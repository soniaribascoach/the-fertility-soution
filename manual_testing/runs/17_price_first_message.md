# 17_price_first_message: Opens cold with 'how much is it'

**What the manual requires:** State the range plainly in the first reply. Do not demand her history before answering, do not get defensive, and do not send a link on message one.

**Manual references:** 2B.2 §6 (never avoid price), 2B.1 §11 (money is not the first filter)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014335_

---

### Turn 1

**Lead:** how much is your program?

**Sonia:**

> My program ranges from $1,500 to $14,000 depending on how much support you need.
>
> It’s one-to-one fertility coaching that looks at your whole situation to find what can still be optimized.
>
> If that fits your budget, I’m here to help when you’re ready.
>

<details><summary>trace</summary>

- intent: `price_question`  tags: `pricing`  language: `en`
- explicit_question: 'how much is your program?'
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `pricing, cant_afford, how_program_works`
- action: `REPLY:price_question`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** that's a big range. what makes the difference between 1500 and 14000?

**Sonia:**

> The difference comes down to how much support and personalization you want.
>
> Some women work with me at a lighter level, focusing on key areas that can move the needle, while others want more frequent sessions and deeper guidance across their whole fertility picture.
>
> It really depends on your goals and how much help you feel you need.
>

<details><summary>trace</summary>

- intent: `price_question`  tags: `pricing`  language: `en`
- explicit_question: 'what makes the difference between 1500 and 14000?'
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `pricing, cant_afford, how_program_works`
- action: `REPLY:price_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- One sentence, the correct range, no history demanded first, no link on message one. Turn 2 answers what the range depends on without deflecting to the call.
