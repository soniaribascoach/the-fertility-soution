# r2_34_post_booking_email: Has booked, gives her email

**What the manual requires:** Send the masterclass, say Natalia will text before the appointment, ask her to reply so it stays confirmed. This is the one scripted sequence in the manual.

**Manual references:** 2B.2 §8 (after someone books), worker `_is_booking_email`

_Run 2026-08-11 14:48 UTC, 2 turns, $0.013653_

---

### Turn 1

**Lead:** booked! for thursday

**Sonia:**

> Great, Thursday is in the calendar.
>
> Which email did you use to book?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `post_booking`  language: `en`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `post_booking_email`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** my email is hannah.reid@example.com

**Sonia:**

> Thank you.
>
> I've sent my masterclass to that address. It's worth watching before Thursday so the call can start further along.
>
> https://www.thefertilitysolution.com/watch-replay
>
> Natalia will text you beforehand. Reply to her so your slot stays confirmed.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `post_booking`  language: `en`
- explicit_question: 'Which email did you use to book?'
- slots: `{"email": "hannah.reid@example.com"}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `post_booking_email`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- F30 closed. All four steps of 2B.2 §8: email asked for, masterclass sent with the URL, Natalia named, reply-to-confirm requested.
- Closed without the gate change the round 3 write-up recommended. `post_booking` is now a tag the reader can set, so the conversation is selected on the tag rather than waiting for a phase the seeded state never reaches.
