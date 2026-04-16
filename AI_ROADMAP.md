# AI Reply Quality — Improvement Roadmap

## Root Cause Analysis

After architecture review, five root causes explain the quality failures (too reflective, not directive, therapy phrases slipping through, generic replies):

| # | Root Cause | Impact |
|---|-----------|--------|
| 1 | Writer system prompt is too crowded — persona + 300-word voice rules + ALL scenario patterns loads every turn, burying the brief | HIGH |
| 2 | Briefs are template-based and don't extract specific anchors — writer sees "do not re-ask" instructions but not "USE HER SPECIFIC DETAILS" | HIGH |
| 3 | Quality gate is mechanical-only — catches em-dashes and therapy phrases, but never checks "is this reply expert/specific/directive?" | HIGH |
| 4 | Briefs are templates, not dynamically adapted — a per-turn LLM-generated brief could reference her exact words and numbers | MEDIUM |
| 5 | No retry loop — quality gate can approve a passable-but-weak reply with no way to flag it for rewrite | LOW-MEDIUM |

---

## Intervention Status

### ✅ Phase 1 — In Progress

**Intervention 1: Slim the writer system prompt** (`app/services/ai.py`)
- Remove ALL scenario patterns from the fixed system prompt — they are already injected per-turn via `_pattern_context()` in the brief
- Condense `_WRITER_VOICE` from ~300 words to ~180 words — remove the "LEAD" and "Be specific" sections (these move to the brief anchors and quality gate enforcement)
- Keep: persona, banned phrases, voice mechanics, one-question rule, zoom session rule

**Intervention 2: Specific anchor injection into briefs** (`app/services/briefs.py`)
- Add `_specificity_anchor(route)` helper that extracts known data points and tells the writer to anchor the reply to her actual situation
- Inject into: `brief_qualify`, `brief_synthesise`, `brief_nurture`, `brief_empathize_qualify`
- NOT injected into: `brief_empathize` (grief turn — specifics would feel clinical), `brief_send_booking`

**Intervention 3: Upgrade quality gate to substantive review** (`app/services/ai.py`)
- Add 3 new checks to the quality gate prompt:
  - **Check 10 (Expert value)**: Does the reply add at least one reframe, insight, or guidance? If not, the gate adds one.
  - **Check 11 (Specificity)**: Is the reply anchored to a specific detail she shared? If not, the gate edits it.
  - **Check 12 (Passivity)**: Is the reply leading or just mirroring? If passive, the gate makes it directive.
- Checks are goal-aware: skipped for `empathize` and `send_booking`; enforced for `qualify`, `synthesise`, `nurture`, `empathize_qualify`, `handle_objection`, `open_context`, `confirm_booking`
- Increase `max_completion_tokens` from 600 → 800 to give the gate room for the additional checks

---

### Phase 2 — Pending (implement only if Phase 1 doesn't sufficiently resolve specificity)

**Intervention 4: Dynamic brief generator / meta-prompt optimizer**
- Add `_generate_dynamic_brief()` as Stage 3B — a cheap gpt-4.1-mini call running in parallel with the tagger
- Input: goal, template brief (starting point), last 4 turns, known_facts, matched pattern
- Output: 10-line hyper-specific brief referencing her actual words and numbers
- The template brief from briefs.py becomes the base; the optimizer refines it
- Cost: +~$0.00015/turn | Latency: +~300ms (parallel — no critical path impact)

---

### Phase 3 — Future

**Intervention 5: Reflexion retry loop**
- If quality gate flags a reply as still failing substantive checks after one edit, route back to writer with explicit critique for one retry
- Cost: ~2x writer call cost | Latency: +~1s
- Hold until Phases 1-2 are evaluated

---

## Verification Protocol

After Phase 1 is deployed:

1. Run `simulate.py` against the `failures.txt` conversation — check that replies add insight, reference her details, don't mirror passively
2. Run a grief-opener scenario (miscarriage T0) — verify T0 is pure empathy, T1 is empathize_qualify, T2 transitions to qualify
3. Run a pricing scenario — verify no price number leaks through `handle_pricing_deflect`
4. Check `prompts.log` — writer system prompt should drop from ~800 to ~400 tokens
5. Check `prompts.log` quality gate section — should now show check 10/11/12 findings
6. Confirm reply tone is directive, not reflective, by T3+