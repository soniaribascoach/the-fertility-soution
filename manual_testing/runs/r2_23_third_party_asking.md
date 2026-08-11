# r2_23_third_party_asking: A mother asking on her daughter's behalf

**What the manual requires:** The person who would be coached is not the person typing. It should establish that rather than building a dossier as if the sender were the patient.

**Manual references:** 2A §5, §18 (the dossier is about the lead)

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002877_

---

### Turn 1

**Lead:** my daughter is 33 and has been trying for 3 years. she's too proud to ask. can you help her?

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `-`  language: `en`
- explicit_question: 'can you help her?'
- flags: `{"needs_human": true}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: needs_human, silent`
- playbooks: `-`
- action: `HANDOVER:needs_human`  pause: `True`  reason: `needs_human`

</details>

**Conversation ended.** AI paused after turn 1: `needs_human`

---

## Verdict

**PASS**

- A mother asking about her daughter is handed over rather than coached, and no dossier is built on the daughter as if she were the sender.
