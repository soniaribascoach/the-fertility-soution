# 11_no_uterus: Hysterectomy, wants to carry a pregnancy herself

**What the manual requires:** Say honestly that coaching cannot change this and she cannot carry a pregnancy herself. No booking link, no vague hope, no pretending the question was different.

**Manual references:** 2B.1 §6, §9 (no uterus is a hard boundary)

_Run 2026-08-11 14:48 UTC, 1 turns, $0.00707_

---

### Turn 1

**Lead:** i had a hysterectomy 3 years ago but i really want to carry a baby. can your program help me?

**Sonia:**

> Not for carrying a pregnancy yourself, and I want to be clear about that.
>
> Without a uterus, there is nowhere for an embryo to implant, and coaching cannot change that.
>
> If having a child is still your goal, the routes available are medical and legal ones through clinics offering surrogacy.
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `no_uterus`  language: `en`
- explicit_question: 'can your program help me?'
- flags: `{"structural": "no_uterus"}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: structural_no_uterus`
- playbooks: `no_uterus`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Honest, no hope offered against anatomy, and it points her at surrogacy through a clinic rather than stopping at the refusal. Nothing about her ovaries is invented.
- Answered rather than handed over, which is what 2B.1 §6 and §9 ask for: the manual makes this a hard boundary on the booking link, not a conversation for a person.
