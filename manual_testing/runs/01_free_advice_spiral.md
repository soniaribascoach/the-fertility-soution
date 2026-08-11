# 01_free_advice_spiral: General questions forever, never a word about herself

**What the manual requires:** Answer briefly, then turn the conversation back to her situation. By the third general-knowledge question the reply should be naming the pattern and offering either the free masterclass or a real conversation, not teaching another module.

**Manual references:** Part 1 §3 (never turn DMs into free coaching), 2B.2 §3, §4, §14, App A.8

_Run 2026-08-11 14:48 UTC, 7 turns, $0.054824_

---

### Turn 1

**Lead:** hi, i was told i have pcos

**Sonia:**

> PCOS can look very different from one woman to another, and just knowing the diagnosis doesn’t give the full picture.
>
> What led to the diagnosis? Was it irregular cycles, cysts on the ovaries, hormone levels, or something else?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `pcos`  language: `en`
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `pcos`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** what should i eat with pcos?

**Sonia:**

> There isn’t a one-size-fits-all list I can give you, because what to eat depends on why your levels and symptoms are the way they are.
>
> Nutrition is just one part of the work, and I’d need to understand more about your case to say what’s most useful for you right now.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, pcos`  language: `en`
- explicit_question: 'what should i eat with pcos?'
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `free_coaching_request, education_spiral, wants_services_i_dont_provide`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 3

**Lead:** how much inositol should i take?

**Sonia:**

> I can’t tell you what dose of inositol to take because that depends on your specific situation and why your levels are where they are.
>
> What I can say is that what to take, how much, and when is part of a personalized plan rather than general advice.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, pcos, supplement_request`  language: `en`
- explicit_question: 'how much inositol should i take?'
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `free_coaching_request, education_spiral, supplement_request`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 4

**Lead:** does exercise help pcos?

**Sonia:**

> Exercise can support managing PCOS by improving insulin sensitivity and hormone regulation, but it’s not a cure on its own.
>
> How you move and how often can make a difference, but what’s most effective depends on your overall health and other factors in your case.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, pcos, supplement_request`  language: `en`
- explicit_question: 'does exercise help pcos?'
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `free_coaching_request, education_spiral, supplement_request`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 5

**Lead:** what about coffee, is caffeine bad?

**Sonia:**

> Caffeine affects everyone differently, and its impact on PCOS can vary from person to person.
>
> Some women find reducing caffeine helps with symptoms, while others don’t notice much change. It’s worth paying attention to how your body responds.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, pcos, supplement_request`  language: `en`
- explicit_question: 'what about coffee, is caffeine bad?'
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `free_coaching_request, education_spiral, supplement_request`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 6

**Lead:** and alcohol?

**Sonia:**

> Alcohol can influence hormone balance and metabolic health, which are important areas in PCOS.
>
> How it affects you specifically is something to observe, as the impact varies between individuals.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, pcos, supplement_request`  language: `en`
- explicit_question: 'and alcohol?'
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `free_coaching_request, education_spiral, supplement_request`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 7

**Lead:** ok thanks, that's all i needed

**Sonia:**

> Glad I could help.
>
> If you want to see the full picture of fertility and how these pieces fit together, my masterclass covers it in one place and is free.
>
> https://www.thefertilitysolution.com/watch-replay
>

<details><summary>trace</summary>

- intent: `gratitude`  tags: `closing, pcos, free_coaching`  language: `en`
- slots: `{"diagnoses": ["pcos"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `conversation_close, education_spiral, free_coaching_request`
- action: `REPLY:gratitude`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PARTIAL**  ·  findings: F16, F19

- The food list is gone. Turn 2, which produced a nutrition plan in every previous round, now says there is no list to give and why.
- Turn 3 refuses the dose cleanly.
- Turns 4, 5 and 6 are still three more free modules, on exercise, caffeine and alcohol, and the masterclass only arrives on turn 7 when she is already leaving. The reader now tags `free_coaching` from turn 2 and keeps it, and the right conversations are selected on every turn, and the writer teaches anyway.
- Turn 7 contains an em dash.
