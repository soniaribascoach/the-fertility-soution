# Which model should write the replies?

**Measured 2026-08-03** with `scripts/compare_writers.py`, over the 12 scenarios in
`tests/brain/scenarios/`, which are Sonia's own reported failures. Only
`model_writer` changed between runs; the classifier and checker stayed on
`gpt-4o-mini` throughout, because the complaint under test is about how replies
READ and that is the writer's job alone. Each figure is the mean of a full pass
after a warm-up pass, so the prompt cache is in steady state.

| writer | passed | silent | specific | tokens/turn | cached | USD / 1000 turns | sec |
|---|---|---|---|---|---|---|---|
| `gpt-4o-mini` | 12/12 | 0 | 0.67, 0.66 | 6,838 | 5,984 | **0.72**, 0.68 | 6.0 |
| `gpt-4.1` | 12/12 | 0 | 0.59 | 6,715 | 4,821 | 4.23 | 4.9 |
| `gpt-5` | 12/12 | 0 | 0.70, 0.67 | 6,632 | 5,749 | **1.93**, 1.88 | 6.3 |

`specific` is the "Specific To Her" GEval judge, which asks Sonia's own Part 3
question: could this reply be pasted into another conversation unchanged?

## The finding contradicts the plan

The plan assumed the model was the bottleneck for voice quality, on the grounds
that her headline complaint was that replies sounded templated. **It is not.**
Two samples per model put `gpt-4o-mini` at 0.66-0.67 and `gpt-5` at 0.67-0.70 -
overlapping ranges, on a 12-case corpus. All three models route every scenario
correctly and none produces a silent turn.

What changed the output was the content work, not the model: the compiled
behavior core, the retrieved playbook examples, and the per-mode question policy.
A mini model with real substance in front of it beats a frontier model with a
script.

`gpt-4.1` is both the most expensive and the weakest of the three here, so it is
not a candidate.

## Recommendation

**Keep `gpt-4o-mini` as the writer default.** It is measurably equivalent on this
corpus and 2.7x cheaper than `gpt-5`.

Two caveats that matter more than the table:

* The absolute difference is small in business terms. At 10,000 DM turns a month
  it is roughly $7 against $19. If Sonia reads both and prefers the `gpt-5`
  prose, switch it and do not agonise - set `model_writer=gpt-5` in AppConfig,
  no deploy.
* The judge measures ONE dimension, specificity, on 12 mostly single-turn cases.
  It is a regression guard, not a verdict on how she sounds. Her review is.

## Prompt caching is doing real work

87% of the writer's input tokens are served from the cached prefix
(5,984 of 6,838). That is the behavior core plus the mode contract, which are
byte-identical across every turn in a mode by design.

It matters most on the models it was least obviously needed for: a cached input
token costs a **tenth** of a fresh one on `gpt-5` and `gpt-4.1`, against a half on
`gpt-4o-mini`. Interleaving anything conversation-specific into that prefix
would forfeit the discount and roughly triple the input cost of a strong writer.

## Choosing a strong writer was not a config change

It is one now, but it was not before this measurement. The GPT-5 family:

* renamed `max_tokens` to `max_completion_tokens` - a hard 400 otherwise;
* accepts only the default temperature, so the writer's 0.7 is a 400;
* draws reasoning tokens from the SAME budget as the reply. At our 500, gpt-5
  spent all 500 thinking and returned nothing at all.

`llm.completion_kwargs` handles all three, with `reasoning_effort="minimal"`
(measured: 0 reasoning tokens) because a DM reply is a writing task and thinking
longer about it buys nothing. Pinned in `tests/brain/test_llm_params.py`.

## Handoff rate

Zero silent turns across every run, at `uncertainty_threshold=3`. The threshold
was documented as a guess; on this corpus it is not suppressing anything, while
the takeover suite confirms the paths that SHOULD reach a human still do. Leave
it at 3 and revisit from shadow-mode traffic, which is the only place a real
handoff rate can be observed.

## Reproducing

```bash
./.venv/bin/python scripts/compare_writers.py                    # mini, 4.1, 5
./.venv/bin/python scripts/compare_writers.py gpt-4o-mini gpt-5  # just the two
```
