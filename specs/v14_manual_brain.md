# The manual brain — Sonia's Operating Manual as the system

**Status:** built on `feat/sonia-v14-manual`, default `brain_version=routed`.
**Supersedes for new work:** [`routed_brain.md`](./routed_brain.md) (still accurate
for the pipeline it describes) and [`brain_architecture.md`](./brain_architecture.md)
(the funnel brain, `brain_version=funnel`, still wired for rollback).
**Source of requirements:** *The Fertility Solution DM AI Operating Manual v1.0*,
2026-08-03, in `current_feedback/`.

---

## 1. The instruction that shaped this

> "The AI loads these behavioral principles as persistent instructions, then
> dynamically retrieves only the relevant playbooks and knowledge for each
> conversation, rather than injecting the entire document into every DM."

The manual is ~87k characters, about 22k tokens. It is compiled, not pasted.

## 2. Three layers, split by who owns them and how often they change

| Layer | Where | Owner | Loaded |
|---|---|---|---|
| Behavior | `app/services/brain/behavior/` | repo, versioned | always, ~1,550 tokens |
| Playbooks | `playbooks` table | **Sonia** | one per turn |
| Knowledge | `knowledge` table | **Sonia** | up to three per turn |

**Behavior** is `core.md` (identity, non-negotiables, how she writes, what she
would never send, how she checks a reply) plus one contract per response mode.
Compression to a tenth of the source is safe because the manual is deliberately
redundant: "answer before qualifying", "never re-ask" and "do not force a
question" each appear in five or more places.

Two categories are deliberately NOT prompt text:

* **Decisions** — Part 2B.1 §6-10 live in `gates.py` as code, so "never qualify a
  grieving woman" is a property the tests prove rather than a sentence a model
  may honour.
* **Facts** — Part 5 lives in the `knowledge` table. Hardcoding them is how the
  running code came to claim 15 years in `writer.py` and "over 700 families" in
  `prompt_builder.py` simultaneously. `test_behavior.py` fails if any business
  fact reappears in `core.md`.

**Playbooks** carry the manual's Standard Playbook Structure. Six of the eleven
fields reach the prompt; the rest are review columns, because every prompt token
is paid on every turn. A playbook's examples become that turn's few-shots, which
is how CELEBRATE, ACKNOWLEDGE and HONEST_DECLINE got exemplars at all — every
transcript in `few_shots/` is a qualification conversation ending in a booking
link, the worst possible thing to show before congratulating someone.

## 3. Pipeline

`turn.py: run_turn_v2`.

| # | Stage | LLM | Module |
|---|---|---|---|
| 0-1 | Safety gate, phase-1 CTA | no | `brain/__init__.py` |
| 2 | Classify | #1 | `classify.py` |
| 3 | Route to one of nine modes | no | `router.py` |
| 4 | Retrieve playbook + knowledge | no | `playbooks.py`, `knowledge.py` |
| 5 | Write | #2 | `writer.py` |
| 6 | Code checks | no | `checks.py` |
| 7 | Veto panel, conditional | #3 | `checker.py` |
| 8 | Uncertainty → a person | no | `uncertainty.py` |

### How many calls, measured

Earlier drafts of this document claimed "two calls typical, three worst case".
That was reasoning from the code, and it is wrong. Measured across the 12
scenarios:

| calls in the turn | turns |
|---|---|
| 2 (classify + write) | 6 |
| 3 | 1 |
| 5 | 5 |

By role: classifier 12, writer 16, `checker:faithful` 4, `checker:premature` 4,
`checker:answered` 2. The writer count exceeds one per turn because a draft that
fails the code checks is regenerated once, and the three judges are separate
calls that run in parallel.

**The ceiling is 6**: classify, write, re-write, and up to three judges. Every
call defaults to `gpt-4o-mini`, overridable per role via `model_classifier`,
`model_writer` and `model_checker`.

Note the corpus is Sonia's reported failures, so it is deliberately weighted
toward hard cases. Real traffic should sit lower, and shadow mode is where that
gets measured.

The writer's system message is `core.md` + the mode contract, in that order,
because it is then byte-identical across every turn in a mode. **87% of writer
input tokens are served from the prompt cache.** Anything conversation-specific
belongs in the user message; moving it into the prefix forfeits the discount.

## 4. Sounding human is mechanical, not requested

| Failure she reported | Mechanism | Where |
|---|---|---|
| Every message ends in a question | per-mode policy, both directions | `checks.py` |
| Same reply across unrelated conversations | opening sentence vs recent sends to other leads | `checks.no_stock_opening` |
| "I hear you", "I get that" | 51 exact phrases from Appendix A | `checks._BANNED` |
| Same rhythm every time | example order rotates on a hash of the lead id | `playbooks.rotate_examples` |
| Generic nutrition/hormones/stress | no positioning claim outside retrieved knowledge | `checks.ground` + `faithful` judge |
| Essays at people who wrote one line | length derived from HER message | `writer.energy_max_chars` |
| Asking what she already said | verbatim-quoted facts + a re-ask check | `classify.py`, `checks.no_reask` |

## 5. Models

Per-role config keys: `model_classifier`, `model_writer`, `model_checker`.
`llm.completion_kwargs` handles the GPT-5 family's renamed parameter, fixed
temperature and shared reasoning budget, so switching is genuinely a config
change.

Measured: the model is **not** the bottleneck. See
[`writer_model_measurement.md`](./writer_model_measurement.md). `gpt-4o-mini`
stays the default.

## 6. Reviewing and growing it

`/admin/shadow` shows what the brain said or would have said, with the mode
distribution at the top as the health check: **if it is almost entirely QUALIFY,
the router is not doing its job.** Every turn is in `brain_turns` with its
routing decision, retrieved knowledge, uncertainty score and per-call cost, and
an aborted turn keeps the draft it refused to send.

Each turn has a **Teach this** control: edit the reply into what she would have
sent, pick a playbook, save. It becomes an example the next matching
conversation learns from, and the playbook stops being marked a draft. That is
Sonia's stated growth path with no developer in the middle.

`/sqladmin → Playbook` and `→ Knowledge` are the direct editors.

## 7. Rollout

`brain_shadow_enabled=1` with `brain_version` still `funnel` runs this brain on
real traffic against a deep copy of lead state, sending nothing. Review, then
flip `brain_version`. Rollback is that one field, no deploy; `funnel` and
`legacy` both remain wired.

## 8. Testing

```bash
pytest -m "not live"    # 540
pytest -m live          # real OpenAI
```

`tests/brain/scenarios/*.yaml` holds Sonia's own reported failures as data, each
carrying her wording so a red test explains itself. Every case runs twice: once
against the router with a stubbed classifier (free, deterministic) and once
end-to-end against the real model.

## 9. Known gaps

* **Parts 4 and 5 are seeded, not finished.** Entries sourced `DRAFT - needs
  Sonia` were written because no prior art existed. Her real conversations
  replace them.
* **Pricing is inactive.** The manual says $1,500-$10,000, the live config says
  $14,000. The entry sits in the table with `active=false` until she confirms.
  Four other manual-vs-code conflicts are open; see the plan file.
* **No Spanish playbooks.** `few_shots/` has no Spanish transcripts either, so ES
  tone will not improve proportionally with EN. A content gap, not a code gap.
* **Nothing has run against live traffic.** The handoff rate is 0% across the
  scenario corpus, which is not the same as 0% on real DMs.
