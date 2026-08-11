# 21_asks_for_human: Asks to speak to a real person

**What the manual requires:** Warm handover. Never 'I don't know' or 'I can't help'.

**Manual references:** 2B.2 §13, flag `asked_for_human`

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002905_

---

### Turn 1

**Lead:** can i speak to an actual person on your team? i have a complicated situation

**Sonia:**

> I want you to get a proper answer on this, so I'm bringing someone from my team in.
>
> They can see everything you've already told me, so you won't need to type any of it again. Someone will come back to you shortly.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `-`  language: `en`
- explicit_question: 'can i speak to an actual person on your team?'
- flags: `{"asked_for_human": true, "needs_human": true}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: asked_for_human, fixed line handover_message_team`
- playbooks: `-`
- action: `HANDOVER:asked_for_human`  pause: `True`  reason: `asked_for_human`

</details>

**Conversation ended.** AI paused after turn 1: `asked_for_human`

---

## Verdict

**PASS**

- The fixed team line, then pause and tag. She asked for a person and is told a person is coming, which is the case where silence would have been the wrong answer.
