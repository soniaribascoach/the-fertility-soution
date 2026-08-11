# r2_26_broken_english: English, but very limited

**What the manual requires:** English so limited that coaching may not work is a documented fit question, and it is a judgement for a person. It must not be rude, and it must not pretend to understand.

**Manual references:** 2A §14 (communication fit, and a language barrier is not intelligence)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014606_

---

### Turn 1

**Lead:** hello mam i want baby 5 year no baby doctor say tube ok egg ok why no baby

**Sonia:**

> Five years trying without a pregnancy, with tubes and eggs reported as okay, definitely deserves a deeper look beyond those basics.
>
> There could be other factors at play that haven’t been fully explored yet, like ovulation quality, hormonal balance, or even the male partner’s side.
>
> I’m a fertility coach, and I help women and couples look at the full picture and find what can realistically be optimized. If you want, I can share a free masterclass that explains this approach in detail.
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `tubal`  language: `en`
- explicit_question: 'why no baby'
- slots: `{"time_trying": "5 year", "diagnoses": ["tube ok", "egg ok"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `blocked_tubes`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** you help me? how much money? i no understand much english sorry

**Sonia:**

> I help women and couples with fertility by looking at their whole health and what can be improved, not just medical tests.
>
> My program costs between $1,500 and $14,000 depending on the level of support you need.
>
> If you want, I can send you a free masterclass in simple English to explain more.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `long_ttc, tubal, egg_quality`  language: `en`
- explicit_question: 'you help me? how much money?'
- slots: `{"time_trying": "5 year", "diagnoses": ["tube ok", "egg ok"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `blocked_tubes, donor_eggs, returning_prospect`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PARTIAL**

- Very limited English is no longer read as `other`, so she is not ejected, which is the half of this that mattered.
- Whether coaching can work through this much of a language barrier is a documented fit question (2B.1 §9, communication not workable) and a judgement for a person. Instead she was quoted the price. Nothing in the reply is wrong; it is answering a question that should have gone to a human.
