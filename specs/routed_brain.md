# Routed Brain — intent classification above the funnel

**Status:** implemented, behind `brain_version=routed`. Not live.
**Supersedes for new work:** [`brain_architecture.md`](./brain_architecture.md), which
describes the funnel brain (`brain_version=funnel`) and is still accurate for it.
**Source of requirements:** Sonia's review email, 2026-07-29.

---

## 1. Why

Sonia tested the funnel brain across the full range of DM scenarios and would not
put it live. Her nine complaints reduce to one architectural fact:

> **The qualification funnel was the only path through the code.**

`controller.decide()` terminates in `_waterfall()` for everything that is not
out-of-scope or a takeover. There was no code path that congratulated a
pregnancy, sat with grief, recognised an existing client, or answered a question
and stopped. So a pregnant woman, a thank-you message and a woman who had decided
to stop trying all entered a sales funnel — exactly as she reported.

Two of her complaints were quotable from the source: the generic
"nutrition, hormones, stress and lifestyle" positioning is `directive.py:139-149`,
and the repeated `"How long have you been trying and what have you already done?"`
is `DISCOVERY_QUESTIONS` handed to the voice as `reference_text`
(`directive.py:226-227`) — identical every time by construction.

Her own prescription is what this builds:

> *"the system needs an intent classification and conversation stage before
> generating each reply... Only after identifying the intent and stage should it
> decide whether to empathize, answer, qualify, educate, provide a resource,
> celebrate or move toward booking."*

---

## 2. Pipeline (`app/services/brain/turn.py: run_turn_v2`)

Same signature and `TurnResult` shape as the funnel brain, so the worker, the
admin sandbox and the tests are unchanged.

| # | Stage | LLM | Module |
|---|---|---|---|
| 0 | Safety gate (config phrases, media URL) | no | reused from `brain/__init__.py` |
| 1 | Phase-1 CTA keyword | no | reused |
| 2 | **Classify** — why she is messaging | **#1** | `classify.py` |
| 3 | **Route** — pick one of nine modes | no | `router.py` |
| 4 | Retrieve approved substance | no | `knowledge.py` |
| 5 | **Write** — per-mode contract | **#2** | `writer.py` |
| 6 | Code checks — rules, grounding, repeats | no | `checks.py` |
| 7 | Veto panel — conditional | **#3** | `checker.py` |
| 8 | Uncertainty → a person | no | `uncertainty.py` |

Two calls on a routine turn; three when something already looks off.

---

## 3. The router — the actual fix (`router.py`)

Nine modes, Sonia's own verbs: `CELEBRATE · ACKNOWLEDGE · ANSWER · EDUCATE ·
RESOURCE · QUALIFY · BOOK · HONEST_DECLINE · HANDOFF`. **QUALIFY is one of nine**,
not the universe.

Evaluation order is the specification; each step exists because something above
it would otherwise swallow the case:

1. conversation already ended → silence
2. unsupported language → silence beats a decline she cannot read
3. hard out-of-scope → facts decide, not the model
4. escalation intents → a human regardless of funnel position
5. cannot tell (`unsure` / `off_script`) → a human
6. **never-qualify intents** → CELEBRATE / ACKNOWLEDGE / HANDOFF
7. after the link is out → two safe turns, then a human
8. **likely not a fit** → honest decline (above the question handler on purpose:
   "should I join?" is answered by the assessment, not by a services description)
9. she asked something → ANSWER / EDUCATE / RESOURCE
10. objections → four distinct conversations
11. gate passes → BOOK
12. otherwise → QUALIFY

`constants.NEVER_QUALIFY` is proven unreachable from QUALIFY and BOOK at every
stage by `tests/brain/test_router.py`, plus a structural guard so a future intent
added without a branch fails to a human rather than silently entering the funnel.

---

## 4. What each piece contributes

**`gates.py`** — booking gate, its predicates, the OOS rules, and
`likely_not_a_fit`. Extracted from `controller.py` as a pure move so **both
brains share one booking gate**. Forking it is the one refactoring mistake that
could put unqualified leads on the calendar.

**`classify.py` (LLM #1)** — intent across Sonia's taxonomy with objection
subtypes split, plus:
- `question_asked` — her literal question, carried forward so the reply can be
  checked for actually answering it.
- `situation_richness` — "rich" ends discovery outright, whatever named slots are
  empty. This is the "4 IVF cycles, diet, supplements, 3 practitioners" case.
- `evidence` — a verbatim quote per fact, **verified as a real substring in code**.
  A model that cannot quote cannot claim. This retired the hand-written
  over-inference patches at `controller.py:180-182` and `:218`.
- `intent_certainty` — discrete `certain|probable|unsure`, **not a float**:
  gpt-4o-mini returns ~0.9 for everything including a contentless "ok".

**`knowledge.py` + `knowledge_seed.py`** — the brain had scripts about its own
process and no knowledge of fertility or Sonia's positioning, which is why it
deflected real questions and sounded like any wellness coach. Entries are
retrieved per turn and the writer may not make a fertility or positioning claim
outside them. Seeded from `prompt_pattern_responses` (11 reframes in her voice,
written by the client in April 2026, **read by nothing since Gen 2**) and the Gen 2
system prompt. `prompt_about` / `prompt_services` were deliberately excluded —
generic third-person agency copy listing services she does not offer. Editable at
`/sqladmin → Knowledge`.

**`writer.py` (LLM #2)** — per-mode contracts. Question policy is the headline:
`FORBIDDEN` for CELEBRATE, ACKNOWLEDGE, RESOURCE and HONEST_DECLINE; `REQUIRED`
for QUALIFY. Enforced in **both** directions — the old validator capped at one
and never permitted zero, which is why every reply ended in a question. Few-shots
come from the real `few_shots/` transcripts via `select_few_shots` (written in
Gen 2, **never once called**), truncated before the first Sonia turn containing a
URL unless the mode permits a link. That truncation is the surgical fix for Gen 2's
link-spam prior. The URL is physically absent from the prompt unless permitted.

**`checks.py`** — hard rules, grounding (invented numbers and emails; decimals are
always checked because an AMH of 0.6 is a lab value), no-repeat within a
conversation, and no re-asking a known fact.

**`checker.py` (LLM #3)** — a **veto panel, not a jury**: majority voting is wrong
for safety-asymmetric calls. Three narrow binary judges — `faithful`, `answered`,
`premature` — run only when something already looks off.

**`uncertainty.py`** — one score, one `uncertainty_threshold` in app_config,
tunable without a deploy. Replaces roughly six scattered takeover paths.

---

## 5. Calibration notes (learned from real runs, not guessed)

- A **fabricated quote** (offered and not present in her message) and an
  **unevidenced inference** (no quote offered) are scored differently. The latter
  is routine — the model likes to conclude `diagnosis="none"` from a message that
  never mentions one — and charging for it flagged every ordinary turn.
- **Two failed attempts → send nothing.** Without it a banned phrase or a second
  question survived both passes and went out anyway.
- The **`premature` judge is given the retrieved knowledge**. The approved pricing
  answer legitimately points to the call, and without that context the judge
  vetoed its own approved substance.
- **A knowledge entry must not promise more than the table contains.** The seed
  `not_a_fit` copy told the writer to say what was worth doing on her own; nothing
  in the table supported that, so the writer invented cycle-tracking advice and the
  `faithful` judge vetoed the whole reply. The entry was narrowed, not the judge.
- **`\bdosage\b` silently missed "dosages"** — the more natural phrasing, and the
  one that slipped through a live run. Plurals now covered. Note the check targets
  a number with a unit: "I don't give dosages over DM" is the correct thing to say,
  so the word itself must not be treated as the offence.

---

## 6. Config

| Key | Purpose |
|---|---|
| `brain_version` | `routed` \| `funnel` \| `legacy`. Rollback is this field, no deploy. |
| `brain_shadow_enabled` | `1` runs the routed brain alongside the live one without sending. |
| `uncertainty_threshold` | Integer, default 3. Lower = more handoffs. |
| `model_classifier` / `model_writer` / `model_checker` | Per-role model override. |

## 6b. Reviewing turns

Every turn is recorded in `brain_turns`: the routing decision, the retrieved
knowledge, the uncertainty score and per-call cost. An aborted turn keeps the
draft it refused to send, since that is the most useful thing to review and is
invisible otherwise.

- **`/admin/shadow`** — the review surface. Lead message, what the routed brain
  said, and (in shadow) what was actually sent, side by side. The mode
  distribution at the top is the health check: if it is almost entirely QUALIFY,
  the router is not doing its job.
- **`/sqladmin → Brain Turns`** — filtering and the raw JSON trace.

**Shadow rollout:** set `brain_shadow_enabled=1` while `brain_version` stays
`funnel`. The routed brain then runs on real traffic with a deep copy of the
lead's state, so it cannot move anyone's funnel position, and nothing it writes is
sent. Review `/admin/shadow` with Sonia, calibrate `uncertainty_threshold` from
the observed handoff rate, then set `brain_version=routed`.

All existing funnel keys still apply.

---

## 7. Testing

`pytest -m "not live"` · `pytest -m live` (real OpenAI).

The classifier and end-to-end suites are built from **Sonia's own examples** —
each case is something she reported broken — so they are the contract with the
client rather than developer-invented scenarios.

---

## 8. Known gaps

- **Few-shots are the next pass.** Tone currently comes from the Gen 2
  transcripts plus retrieved substance. CELEBRATE, HONEST_DECLINE and BOOK use no
  few-shots at all because none exist that fit those modes.
- **`few_shots/` has no Spanish transcripts**, so ES tone will not improve
  proportionally with EN. A content gap, not a code gap.
- **The `not_a_fit` seed entry has no prior art** in the repo and is marked
  `NEEDS SONIA REVIEW` in `knowledge_seed.py`. It deliberately says nothing about
  what she could do on her own, because the table holds no guidance to draw on.
  Add a `boundary` or `answer` entry with real content and it can say more.
- **Nothing has run against live traffic yet.** The handoff rate at
  `uncertainty_threshold=3` is a guess until shadow mode produces data; that
  number is the first thing to tune.
