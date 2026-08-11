# 09_age_47_review: 47, two failed IVF cycles, asks to work together

**What the manual requires:** Route to a human rather than booking or rejecting her automatically.

**Manual references:** 2B.1 §10 (age 46-48 needs human review)

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002909_

---

### Turn 1

**Lead:** i'm 47, been trying 2 years, two failed IVF rounds with my own eggs

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `long_ttc, ivf_failed`  language: `en`
- slots: `{"age": 47, "time_trying": "2 years", "ivf_history": "two failed IVF rounds with my own eggs"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: age_needs_review, silent`
- playbooks: `-`
- action: `HANDOVER:age_needs_review`  pause: `True`  reason: `age_needs_review`

</details>

**Conversation ended.** AI paused after turn 1: `age_needs_review`

---

## Verdict

**PASS**

- Silent handover on `age_needs_review`. She is neither booked nor rejected by the machine, which is what 2B.1 §10 asks for.
