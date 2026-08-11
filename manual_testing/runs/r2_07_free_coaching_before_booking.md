# r2_07_free_coaching_before_booking: Wants the plan first, says she will book afterwards

**What the manual requires:** This is the free coaching request in its most reasonable-sounding form. Give the shape of the work, not the work.

**Manual references:** 2B.2 §3, §4, §14

_Run 2026-08-11 14:48 UTC, 3 turns, $0.023592_

---

### Turn 1

**Lead:** before i book, can you just tell me what you'd actually do in my case? 37, 4 years, unexplained

**Sonia:**

> There’s no way to know what would make the biggest difference without looking at everything in your story and health history.
>
> Four years with unexplained infertility and the same tests everyone gets is a clear sign there’s more to explore.
>
> That’s the kind of case where I help find what’s been missed and turn it into a plan you can follow consistently.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `thinking_about_it, unexplained`  language: `en`
- explicit_question: "can you just tell me what you'd actually do in my case?"
- slots: `{"age": 37, "time_trying": "4 years", "diagnoses": ["unexplained"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: first_exchange`
- playbooks: `conversation_close, education_spiral, returning_prospect`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** i don't want to waste a call finding out you'd say the same as everyone else. give me the first 3 things

**Sonia:**

> I get that, and it’s exactly why I can’t give you a quick list.
>
> What you need is specific, not a generic checklist, and I can’t build that without the full picture.
>
> Four years trying with unexplained usually means the basics came back normal but deeper layers weren’t explored—and that’s what I’d want to look at first.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, unexplained, long_ttc`  language: `en`
- explicit_question: 'give me the first 3 things'
- slots: `{"age": 37, "time_trying": "4 years", "diagnoses": ["unexplained"]}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `free_coaching_request, education_spiral, returning_prospect`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 3

**Lead:** if you can't tell me anything specific, what am i paying for?

**Sonia:**

> You’re paying for someone to go beyond the surface and really understand your unique situation.
>
> It’s about identifying what hasn’t been looked at closely enough and helping you take consistent action on that.
>
> This is a personalized, research-backed approach that fits your life and your body, not just general advice.
>

<details><summary>trace</summary>

- intent: `price_question`  tags: `unexplained, long_ttc, thinking_about_it`  language: `en`
- explicit_question: "if you can't tell me anything specific, what am i paying for?"
- slots: `{"age": 37, "time_trying": "4 years", "diagnoses": ["unexplained"]}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `returning_prospect, conversation_close, education_spiral`
- action: `REPLY:price_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**  ·  findings: F19

- F33 closed here, and this was the worst case of it. Turn 1 no longer recites the contents page, turn 2 refuses to name three things and gives her an observation about her own four years instead, turn 3 answers what she is paying for without deflecting to the call.
- No consultation is mentioned in any of the three turns, with the cost unstated, which is the F9 rule holding under the exact pressure that broke it before.
- Turn 2 contains an em dash.
