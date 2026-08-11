# r2_10_age_as_birth_year: Gives a birth year instead of an age

**What the manual requires:** Born 1974 is 52 in 2026. The boundary should apply.

**Manual references:** 2B.1 §9, reader slot `age`

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014536_

---

### Turn 1

**Lead:** i was born in 1974 and i'd still love to have a baby. is that mad?

**Sonia:**

> It’s not mad at all to want a baby. That desire is deeply human and understandable.
>
> At 52, there are real biological limits that coaching can’t change, and it’s important to be honest about that.
>
> If you want, I can share a resource that explains how I work and what options might be realistic for you.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `-`  language: `en`
- explicit_question: 'is that mad?'
- slots: `{"age": 52, "goal_stated": "i'd still love to have a baby"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: age_over_48`
- playbooks: `over_48`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** can we do a call about it?

**Sonia:**

> My work is a paid coaching program that ranges from approximately $1,500 to $14,000 depending on the level of support needed.
>
> If that fits with what you’re looking for, I’m happy to explain more about how to take the next step.
>

<details><summary>trace</summary>

- intent: `warm_prospect`  tags: `thinking_about_it`  language: `en`
- explicit_question: 'can we do a call about it?'
- slots: `{"age": 52, "goal_stated": "i'd still love to have a baby"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: age_over_48`
- playbooks: `returning_prospect, conversation_close, education_spiral`
- action: `REPLY:warm_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PARTIAL**  ·  findings: F9

- F35 closed. Born 1974 is now read as 52, and the writer says 52 back to her. The current year is stated at the top of `70_read.md`.
- Turn 2 answers "can we do a call about it?" with the price range and an offer to explain the next step. She has just been told coaching cannot help her at 52, so there is no next step to explain, and quoting a price to someone who has been ruled out reads as a sales reflex.
