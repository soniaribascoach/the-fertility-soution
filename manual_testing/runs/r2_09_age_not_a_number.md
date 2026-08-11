# r2_09_age_not_a_number: Over 48 without ever typing a number

**What the manual requires:** The age boundary should apply to a woman who is 49, however she says it. If it only fires on an integer, 'late forties' walks straight through.

**Manual references:** 2B.1 §9 (age over 48), dossier `_booking_blocked` checks `isinstance(age, int)`

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002874_

---

### Turn 1

**Lead:** hi sonia, i'm in my late forties and we're still hoping for our first

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `thinking_about_it`  language: `en`
- flags: `{"needs_human": true}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: needs_human, silent`
- playbooks: `-`
- action: `HANDOVER:needs_human`  pause: `True`  reason: `needs_human`

</details>

**Conversation ended.** AI paused after turn 1: `needs_human`

---

## Verdict

**PASS**

- "Late forties" produces no guessed integer, `age` is omitted and `needs_human` is set on line 8. A boundary that would turn her away no longer rests on a number nobody gave.
