# AI Brain Architecture — The Fertility Solution DM Bot

**Status:** implemented & tested (106 tests passing), active behind a config flag.
**Read this first if you're a new session.** This single document is the full
context for the qualification-funnel "brain" that generates Sonia's DM replies.
Source of product requirements: [`sonia_feedback_spec.md`](./sonia_feedback_spec.md).
All brain code lives in `app/services/brain/`.

---

## 0. Orientation (how to use this doc)

- The brain turns an inbound Instagram DM into Sonia's next reply.
- Its #1 goal: **qualify leads and protect the calendar** — never book too early,
  never hallucinate links/prices/medical advice, never sound like a script robot.
- It went through **two designs**: v1 (fully scripted) → paused for feeling robotic;
  v2 (**Soft Director + Generative Voice**, current) fixed that. This doc describes v2.
- If you're changing behavior: the **flow/gates are deterministic code** (`controller.py`),
  the **words are generated** (`voice.py`), and the **guardrails are code** (`validator.py`).
  Change the right layer.

---

## 1. Context & history

The original monolithic-prompt bot (`app/services/ai_pipeline.py` + `prompt_builder.py`,
still present but inactive) was **paused** because it flooded the calendar: booked too
early, over-explained, over-empathized, repeated answered questions, gave advice too soon.

**v1 rebuild** — a deterministic funnel that emitted *verbatim* scripts for every step.
It fixed the calendar problems but **felt like a script robot** and couldn't react to what
a lead actually said (e.g. fired a sales re-engagement at "it's been hard and discouraging").

**v2 (current)** — keep the deterministic director (what to do, when to book, what's known)
but **generate every message** grounded in the conversation, with the approved language as
guidance and hard guardrails in code. Determinism moved out of the *words* and stayed in
the *flow*.

---

## 2. Core principle

> The LLM is a **data processor and a voice**, never the decision-maker.
> Flow control, the booking gate, and the guardrails are deterministic code.
> The wording is generated and grounded in what the lead said.

This is the research-backed pattern for high-ticket sales qualification: probabilistic
understanding (LLM reads language) + deterministic routing (code controls the flow) +
verbatim/validated output (no hallucinated links, prices, or medical advice).

---

## 3. The per-turn pipeline (`app/services/brain/__init__.py: run_turn`)

`run_turn(openai_client, history, cfg, lead_state, *, ig_user_id) -> TurnResult`

| # | Stage | LLM? | What it does |
|---|---|---|---|
| 0 | **Safety gate** | No | Media-URL message, `medical_blocklist` phrase, or `human_takeover_triggers` phrase → pause + tag, short-circuit. |
| 1 | **Phase-1 CTA bypass** | No | If the *only* user message so far exactly equals a `phase1_cta_keywords` entry → return the verbatim `phase1_opening_message`. |
| 2 | **Extractor** | **Yes #1** | Reads recent turns + current slots → strict JSON: slot deltas, `intent`, `situation_type`, `oos_signal`, `takeover`. Never writes user-facing text. `gpt-4o-mini`, temp 0. |
| 3 | **Director** (`controller.decide`) | No | Merges slot deltas; picks the SINGLE next `Action`; enforces the booking gate, OOS/takeover, loop guard, terminal handoffs. |
| 4 | **build_directive** | No | Maps the `Action` → a `TurnDirective`: mode, objective, reference language, `must_include`, `allow_urls`, `allow_price_figure`, `max_chars`, pinned text, and pause/tag/qualified flags. |
| 5 | **Voice** | Voice only | Non-generated actions (OOS declines) return pinned verbatim text; `HUMAN_TAKEOVER` returns no text. Everything else → `voice.generate()` (LLM #2, `gpt-4o-mini`, temp 0.6) → `validate_generated()` → regenerate once at temp 0 → **fall back to the verbatim approved script** if still invalid. |
| 6 | **Finalize** | No | Returns `TurnResult`; the worker sends bubbles, pauses, tags, and persists `lead_state`. |

`TurnResult`: `reply_text`, `pause`, `pause_reason`, `add_tag`, `qualified`, `action`, `usage`, `violations`, `lead_state`.

---

## 4. Module / file map

| File | Role |
|---|---|
| `app/services/brain/__init__.py` | `run_turn` orchestrator + `TurnResult`; safety gate; phase-1 bypass; voice→validate→fallback. |
| `app/services/brain/constants.py` | Shared vocab: `Phase`, `Action`, `Intent` enums; lead-state schema (`SLOT_KEYS`/`FLAG_KEYS`/`COUNTER_KEYS`); `empty_lead_state`, `normalize_lead_state`. |
| `app/services/brain/extractor.py` | LLM #1. Strict JSON via `chat.completions.parse` + Pydantic (`Extraction`, `SlotDeltas`). |
| `app/services/brain/controller.py` | **The Director.** `decide()` state machine, `booking_gate`, `_financial_ok`, `_guard_repeats`, OOS/menopause/takeover, terminal handoffs. Pure, no LLM. |
| `app/services/brain/directive.py` | `TurnDirective` + `build_directive()`: Action→mode mapping, `_GUIDANCE` (short varied reference), `_explain_role_style` (A/B picker), URL/price/length constraints. |
| `app/services/brain/voice.py` | LLM #2. `generate()` writes the message from a directive + few-shots + Sonia persona; smart-quote/dash normalization. |
| `app/services/brain/scripts.py` | The verbatim **reference + fallback + pinned** library: every approved message keyed by `Action`, empathy variants, discovery questions, follow-ups, config placeholders + `render()`. |
| `app/services/brain/validator.py` | `validate()` (verbatim check) + `validate_generated()` (mode-aware guardrails on generated text). |
| `app/worker.py` | `_run_brain_turn` — calls `run_turn`, applies side effects (send/split/typing, pause, tag, persist). Behind the `brain_version` flag. |
| `app/api/admin/router.py` (`/admin/chat`) | Sandbox: calls `run_turn` synchronously, round-trips `lead_state`. |
| `app/repositories/user_state.py` | `get_lead_state` / `save_lead_state` (persist funnel state on the `user_state` row). |

Legacy (inactive, kept for rollback): `ai_pipeline.py`, `prompt_builder.py`, `output_parser.py`, `pricing_classifier.py`.

---

## 5. Lead-state schema (`constants.py`, persisted on `user_state.phase` + `user_state.qualification` JSON)

Carried forward turn-to-turn (never recomputed from scratch). `normalize_lead_state` guarantees all keys exist.

**Slots** (facts, extracted): `trying_duration`, `age`, `treatment_path` (natural|iui|ivf|deciding),
`what_tried`, `done_testing`, `diagnosis`, `diagnosis_detail`, `priority_score` (1-10),
`strong_readiness`, `understands_role`, `open_to_holistic`, `financial_ready`,
`partner_status` (couple|solo|donor|single_by_choice), `partner_is_decision_maker`,
`partner_can_join`, `email_collected`, `closer_assigned`, `tubes_blocked` (none|one|both),
`no_period_reason`, `ivf_interest`.

**Flags** (progress/control): `booking_sent`, `masterclass_sent`, `explained_role`,
`asked_priority`, `situation_shared`, `handed_off` (conversation ended), `cost_declined`
(she can't afford), `last_prompt` (loop guard), `oos_reason`, `takeover_reason`.

**Counters**: `price_ask_count`, `advice_push_count`, `priority_reengage_count`, `repeat_count`.

---

## 6. The qualification funnel

**Waterfall order (in `controller._waterfall`)** — the deterministic path to a booking:
`DISCOVERY → PRIORITY → EXPLAIN_ROLE → FINANCIAL → PARTNER → BOOKING`.
Each step only fires if the previous is satisfied; the lead's answers fill slots that
advance the waterfall. Facts volunteered out of order are captured (no re-asking).

**Discovery** asks the next *missing* question from `[trying_duration, age, treatment_path,
done_testing, diagnosis]` (only the first missing one), acknowledging what she shared.
Complete when `trying_duration AND age AND (treatment_path OR what_tried)`.

**Priority ladder** (never loops): ask 1-10 → if score < 8: re-engage (once) → info-gathering
probe (once) → `NURTURE_CLOSE` (masterclass + soft goodbye + **pause**). An emotional non-answer
(no number) is acknowledged and gently re-asked, **not** treated as a low score.

**Explain-role** always fires once (even if she pre-stated holistic interest, else the gate's
`explained_role` never passes). Two interchangeable styles picked per-lead (`_explain_role_style`):
(A) "I'm a coach, not a doctor…" disclaimer, or (B) Sonia's team's "Have you considered working
with a fertility coach to help elevate your chances?" — a "yes" to either satisfies the step.

**Financial** — a soft check. `financial_ready` is set **only on explicit money openness**
(not general enthusiasm like "count me in"). Asking about price counts as financial engagement
(sets `financial_ready=True`), so it isn't re-asked. "I'll ask my partner" → `partner_is_decision_maker`
(the money decision happens on the call).

**Partner** — assume couple unless told otherwise. Couple → ask if partner can join; if the
partner is the decision-maker and won't attend → pushback (no booking). Solo/donor/single-by-choice → proceed.

**The booking gate** (`booking_gate`) — `SEND_BOOKING` is only reachable when **ALL** are true:
`situation_shared`, actively TTC, priority ok (score ≥ 8 **or** `strong_readiness`),
`explained_role`, `open_to_holistic`, `_financial_ok`, no `oos_reason`, partner resolved.
`_financial_ok` = `financial_ready is True` **OR** (`partner_is_decision_maker` and not explicitly declined).

**Booking is terminal.** `SEND_BOOKING` sends the link + asks for the email, then immediately
**pauses + tags "qualified / link sent" + `handed_off=True`** → the AI goes silent. A human
verifies the email and sends prep (the AI can't verify emails). The `POST_BOOKING_*` scripts
exist but are no longer reached.

---

## 7. Deterministic guarantees (the invariants — enforced in code, covered by pure tests)

1. **Never books before qualified** — the booking link is only emitted when `booking_gate` passes; the validator rejects the link otherwise.
2. **Never repeats an answered question** — discovery asks only the first missing slot; slots carry forward.
3. **Loop guard** (`_guard_repeats`) — the same question is never asked a 3rd time in a row → `HUMAN_TAKEOVER("stuck_repeating")`.
4. **Priority never loops** — bounded ladder ending in `NURTURE_CLOSE`.
5. **Terminal ends** — booked → qualified handoff; not-ready → nurture close; both set `handed_off` → `decide` early-returns silent `_ended`.
6. **Can't-afford-but-keeps-engaging** — a cost decline sets `cost_declined`; the next message → `HUMAN_TAKEOVER("cant_afford_engaging")`.
7. **No hallucinated content** — validator (§12) blocks links/prices/medical-advice out of context; anything that fails twice falls back to the verbatim approved script.

---

## 8. Human-takeover & out-of-scope triggers

All end the turn with `pause=True` + a review tag. Covered by `tests/brain/test_takeover.py` (live).

**Deterministic (code, from extracted slots — do NOT rely on the LLM flag):**
- **Age > 46** → `OOS_AGE_OVER_46` (46 exactly still continues). *This was a real bug: it used to rely on the LLM's `oos_signal` and missed age 48.*
- **Both tubes blocked** (`tubes_blocked == "both"`) → `OOS_BOTH_TUBES`.
- **Menopause** (age-first): 40+ with a menopause/no-period signal → `OOS_MENOPAUSE`; < 40 asks the reason then continues if benign.
- **Can't afford but keeps engaging** → takeover (see §7.6).
- **Stuck/repeating** → takeover (loop guard).

**LLM-judged (via `extractor.takeover`):** "is this AI/a bot?", angry/challenging, severe
distress, wants Sonia directly before qualifying, asks for an exception / to skip the process,
asks for medical advice needing a diagnosis, confused/frustrated ("I already told you").
*Mild venting ("it's been hard") is NOT takeover.* Contradictory info / complex medical case
also route here but aren't in the deterministic test set.

**Config phrase gate (Stage 0):** any phrase in `human_takeover_triggers` or `medical_blocklist`
also pauses (a separate, admin-editable safety net).

**OOS declines (`OOS_*`) are sent VERBATIM** (not generated) — sensitive language stays exact.

---

## 9. Pricing behavior

- Price is **deflected** on the first ask (no number), redirecting to fit.
- On the **2nd ask** → reveal the range (`price_range`, default **"$1,500 to $14,000"**, config-overridable). 3rd+ → firm restate pointing to the call.
- Asking about price = financial engagement → `financial_ready=True` (don't re-ask the financial question).
- **If she's declined on cost (`cost_declined`), she is handed to a human — never gets a price range.**
- The price figure only ever appears in `PRICE_RANGE` / `PRICE_RANGE_FIRM`; the validator blocks `$`+digits everywhere else.
- (Client decision reversed mid-project: ranges were removed, then re-enabled "after 2 asks".)

---

## 10. The Extractor (LLM #1 — `extractor.py`)

- Input: last ~8 turns + current known slots. Output: strict Pydantic `Extraction`
  (`slot_deltas`, `intent`, `situation_type` ∈ hopeless|neutral|misfortune|none, `oos_signal`,
  `takeover`, `takeover_reason`, `confidence`) via OpenAI structured outputs, temp 0.
- **Cardinal rule in its prompt:** only set a slot the lead *explicitly* stated; else null. Never infer.
- Key nuances baked into the prompt: "doing this alone" → solo (not a money refusal);
  "ask my partner" → partner decision-maker (not a refusal); a "yes" to the fit/coach question
  → `open_to_holistic`; `financial_ready` only on explicit money openness; tight-budget + price
  question = `not_ready_no_money`; mild emotion ≠ distress.
- `SlotDeltas` fields must all be in `SLOT_KEYS`; `Intent` literal must match the enum (drift-guarded by tests).

---

## 11. The Voice (LLM #2 — `voice.py`)

- The only user-facing generative surface. Writes 1-3 sentence, texting-style, warm replies
  grounded in the `TurnDirective` (objective, `known_facts`, `still_needed`, reference substance)
  + few-shot examples (which model acknowledging medical/emotional/financial disclosures).
- **Hard rules in the prompt:** acknowledge what she said; ≤1 question; no medical advice;
  only the allowed link(s); never invent facts; plain text (no markdown/em-dash);
  **banned templated openers** ("Thank you for sharing", "I'm glad to hear", "I appreciate your
  honesty", "I admire", …); vary wording; light human imperfections (occasional lowercase/
  fragments) but never mangle a link/number/the disclaimer. `gpt-4o-mini`, temp 0.6.
- `_normalize()` straightens smart quotes and dashes.
- Model choice: kept on `gpt-4o-mini` (client decision). It resists heavy "messiness"; a stronger
  model is the lever if noticeably-messier tone is ever wanted.

---

## 12. The Validator + fallback (`validator.py`)

`validate_generated(directive, text)` — runs on every generated message:
- **URL allowlist** — any URL must be in `directive.allow_urls`; otherwise reject.
- **Price gating** — `$`+digits only if `allow_price_figure`.
- **`must_include`** — required substrings present (booking/masterclass URL, closer phone, price figure).
- **Disclaimer** — if the directive pins it, the "not a doctor" phrase must appear.
- **No medical advice** — regex denylist (`\d+ ?(mg|mcg|iu)`, "milligram", "dosage"); *"prescribe"/"protocol" are excluded* — they appear in Sonia's own disclaimer; the GEval judge is the semantic backstop.
- **Format/length** — no markdown/em-dash, ≤1 question, ≤ `max_chars`.

On failure → **regenerate once at temp 0 → fall back to the verbatim approved script**
(`scripts.render(fallback_action)`). Worst case = v1's safe scripted behavior; best case = a
natural, reactive message.

---

## 13. Config keys (admin-editable via `/sqladmin → AppConfig`)

| Key | Purpose |
|---|---|
| `brain_version` | `funnel` (new brain, active) or `legacy` (old monolith) — **instant rollback**. Seeded `funnel`. |
| `qualified_tag_id` | ManyChat tag id applied on the qualified/link-sent handoff. **Set this to the real tag id** (falls back to the review tag `86596410` if unset/non-numeric). |
| `phase1_cta_keywords`, `phase1_opening_message` | CTA keywords + the exact branded opener. |
| `human_takeover_triggers`, `medical_blocklist`, `medical_deflection` | Stage-0 phrase safety net. |
| `default_closer` (natalia|monika), `closer_assignment` (round_robin) | Closer routing (mostly moot now that booking hands off before confirmation). |
| `booking_link`, `masterclass_register_link`, `masterclass_replay_link`, `website_link`, `ig_highlights_link`, `natalia_phone`, `monika_phone`, `price_range` | Script placeholder overrides (defaults in `scripts.py`). |

---

## 14. Integration & infrastructure (reused, unchanged)

Inbound DM → `POST /webhook` (signature, dedup) → `pending_messages` queue →
`app/worker.py` poller (debounce ~15s, batches per user) → `_handle_conversation`:
checks pause, locks batch, then **if `brain_version == funnel`** → `_run_brain_turn` →
`run_turn` → send bubbles (`split_reply` + typing delays via ManyChat) → `pause_ai` if paused →
`add_tag` (qualified vs review) → `save_lead_state` + `save_message`. Admin sandbox
`/admin/chat` calls `run_turn` synchronously and round-trips `lead_state` (shows a phase chip).

---

## 15. Decisions log (what was chosen and why)

- **Soft director + generative voice** over full-script or full-LLM — keeps qualification integrity while sounding human.
- **Pin only sensitive language** (OOS declines verbatim; disclaimer/price/URLs required-but-generated) — everything else generated.
- **Keep `gpt-4o-mini`** for both calls (cost) — invest in prompt/few-shots for warmth.
- **Booking hands off at the link** (not after an AI email/confirmation dance) — the AI can't verify emails.
- **5a is a like-for-like alternate for the disclaimer** — the "not a doctor" line is no longer hard-required (for ~half of leads it isn't said; accepted trade-off).
- **Price ranges: removed → re-enabled after 2 asks** (client reversed).
- **Deterministic triggers must not depend on LLM flags** — age/tubes checked from the extracted number/slot (the age-48 miss).
- **`financial_ready` only on explicit money openness** — enthusiasm ("count me in") is about coaching, not money.
- **Light human imperfections** in the voice, but never on links/numbers/disclaimer.

---

## 16. Testing

- **Run:** `pytest -m "not live"` (fast, deterministic, no API) · `pytest -m live` (real OpenAI + DeepEval; needs `OPENAI_API_KEY`) · `pytest` (all, ~106 tests).
- **Deterministic (pure):** `test_controller.py` (the funnel/gates/loop-guard/triggers), `test_directive.py`, `test_scripts.py`, `test_validator.py`, `test_generative.py` (validator fallbacks), `test_extractor_schema.py`.
- **Live (real calls):** `test_extractor.py` (slot extraction), `test_run_turn.py` (full-funnel end-to-end), `test_takeover.py` (all 10 triggers), `test_eval.py` (DeepEval GEval judges: no-medical-advice, faithful-memory).
- **Philosophy:** real AI calls, not mocks; guarantees that matter live in deterministic tests; the LLM judge covers what regex can't (tone/hallucination).

---

## 17. Deploy & rollback

- Migrations: `alembic upgrade head` (adds `user_state.phase` + `user_state.qualification`; seeds `brain_version=funnel`, `default_closer=natalia`). Local dev DB is Postgres `fertility_dm`.
- **Before go-live:** set `qualified_tag_id` to the real ManyChat tag.
- **Rollback:** set `brain_version=legacy` in AppConfig (instant; no deploy). Legacy modules remain.

---

## 18. Known limitations / how to extend

- Voice tone caps out at `gpt-4o-mini`'s ability; upgrade the voice model for richer tone.
- "Contradictory info" / "complex medical case" takeovers rely on LLM judgment (no deterministic test).
- The `POST_BOOKING_*` scripts are dormant (booking hands off before them) — a human does post-booking.
- **To add a funnel step:** add the `Action` (constants) + script (`scripts.py`) + wire it in `controller._waterfall` + a `_ModeSpec`/`_GUIDANCE` entry (`directive.py`) + tests.
- **To change wording:** edit `scripts.py` (fallback/verbatim) and/or `_GUIDANCE` (voice reference); the voice paraphrases the reference.
- **To add a hard rule:** add a check in `validate_generated` (`validator.py`).
- **Follow-up sequences** (`scripts.FOLLOWUPS`) exist but are not wired into the live turn flow (scheduler territory).
