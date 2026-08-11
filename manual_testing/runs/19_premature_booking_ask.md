# 19_premature_booking_ask: First message is 'I want to book'

**What the manual requires:** Do not send the link on message one with nothing known. Ask what is going on for her first, then invite her once there is enough to justify it.

**Manual references:** 2B.2 §7 (book only once basic fit is established), 2B.1 §15

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014634_

---

### Turn 1

**Lead:** hi! how do i work with you? i want to book a call

**Sonia:**

> I work one-to-one as a fertility coach, helping women and couples optimize fertility through a personalized, research-backed approach that looks at the full picture.
>
> The program is paid, with prices ranging from about $1,500 to $14,000 depending on the level of support you need. It runs alongside any medical care you may be having, never instead of it.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `ready_to_book`  language: `en`
- explicit_question: 'how do i work with you?'
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `ready_to_book`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** i've been trying for 3 years, i'm 34, one failed IVF. it's the only thing i want

**Sonia:**

> Three years and a failed IVF cycle is a lot to carry, especially when it’s your main focus.
>
> There may still be meaningful areas to explore that haven’t been addressed yet, which could make a difference.
>
> If you’re ready, I can send you the link to book a free consultation with my team. They’ll take a full history and decide whether I can help you.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `ivf_failed, long_ttc, ready_to_book`  language: `en`
- slots: `{"age": 34, "time_trying": "3 years", "ivf_history": "one failed IVF", "pregnancy_priority": "high"}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `ready_to_book, returning_prospect, first_message_vague`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- F9 closed here, and this is the run it was raised on. Turn 1 answers "how do I work with you" with what the work is and what it costs, and mentions no call at all.
- Turn 2 offers the link only after the price has been stated, which is the ordering rule in `30_operations.md` finally holding.
- The intermediate attempt is worth recording: with the prohibition alone, the model wrote "since you know what it costs" into a conversation where the cost had never been mentioned. Telling it what the turn is *for* is what fixed it.
