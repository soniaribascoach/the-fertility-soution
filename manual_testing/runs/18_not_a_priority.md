# 18_not_a_priority: Not trying yet, just curious

**What the manual requires:** Answer honestly that she probably does not need this yet, and do not push toward booking. Manufacturing urgency about her age would be a serious failure.

**Manual references:** 2A §9, 2B.1 §9 (pregnancy is not a priority)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.01421_

---

### Turn 1

**Lead:** hi! i'm 29, not trying yet, maybe in 3 or 4 years. just curious what you actually do

**Sonia:**

> I help women and couples who are trying to conceive or preparing for treatments like IVF work out what might still be optimized in their fertility.
>
> That means looking beyond just one test or diagnosis to the full picture of health and biology, and supporting consistent action to improve it.
>
> At your stage, not trying yet, this kind of intensive work usually isn’t needed. When it’s real for you, I’m here to help.
>
> Meanwhile, my free masterclass covers what’s worth knowing before you start trying: https://www.thefertilitysolution.com/watch-replay
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `not_priority`  language: `en`
- explicit_question: 'just curious what you actually do'
- slots: `{"age": 29, "time_trying": "not trying yet, maybe in 3 or 4 years"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `not_a_priority_yet`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** should i be worried about waiting that long?

**Sonia:**

> At 29 and not trying yet, there’s no need to be worried about waiting three or four years.
>
> Your body is still young and there’s time to prepare when you’re ready.
>
> If you want a clear idea of what matters before you start, my masterclass can give you a solid foundation: https://www.thefertilitysolution.com/watch-replay
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `not_priority`  language: `en`
- explicit_question: 'should i be worried about waiting that long?'
- slots: `{"age": 29, "time_trying": "not trying yet, maybe in 3 or 4 years"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `not_a_priority_yet`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- F33 closed here. Turn 1 says what the work is for in one sentence rather than reciting the contents page, and then says honestly that a 29-year-old who is not trying does not need it.
- No manufactured urgency on turn 2, and the masterclass link is in both messages rather than offered and withheld.
- The `not_priority` tag now fires, so `not_a_priority_yet` is the conversation the reply is written from. In round 3 this turn was tagged `thinking_about_it` and pulled three unrelated files.
