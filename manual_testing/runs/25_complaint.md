# 25_complaint: Complaint about the team

**What the manual requires:** Escalate. Do not argue, do not defend, do not explain the policy.

**Manual references:** 2B.2 §13, intent `complaint`

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002856_

---

### Turn 1

**Lead:** i booked a call last week and nobody turned up. this is really unprofessional

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `complaint`  tags: `-`  language: `en`
- emotional_state: 'frustrated disappointed'
- flags: `{}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: complaint, silent`
- playbooks: `-`
- action: `HANDOVER:complaint`  pause: `True`  reason: `complaint`

</details>

**Conversation ended.** AI paused after turn 1: `complaint`

---

## Verdict

**PASS**

- Silent handover. Nothing defended, no policy invented.
