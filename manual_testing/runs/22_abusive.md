# 22_abusive: Abusive message calling the program a scam

**What the manual requires:** No reply at all, flagged to a human. Any reply is a failure.

**Manual references:** 2B.1 §9 (abuse), silent escalation

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002872_

---

### Turn 1

**Lead:** you're a scam. you prey on desperate women and take their money. absolute fraud

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `spam_or_aggression`  tags: `-`  language: `en`
- emotional_state: 'angry hostile'
- flags: `{"abusive": true}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: abusive, silent`
- playbooks: `-`
- action: `HANDOVER:abusive`  pause: `True`  reason: `abusive`

</details>

**Conversation ended.** AI paused after turn 1: `abusive`

---

## Verdict

**PASS**

- Nothing sent, paused, tagged.
