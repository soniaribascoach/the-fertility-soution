# 32_pregnancy_announcement: Announces a pregnancy

**What the manual requires:** Celebrate. No qualification, no program, no link, no 'and afterwards...'.

**Manual references:** Part 1 §8 (celebrate, do not qualify), intent `pregnancy_announcement`

_Run 2026-08-11 15:17 UTC, 2 turns, $0.01412_

---

### Turn 1

**Lead:** SONIA!!! i'm pregnant!!! after 4 years!! i can't believe it

**Sonia:**

> Congratulations! That is incredible news after such a long journey.
>
> Take a moment to let that sink in and enjoy it. How are you feeling?
>

<details><summary>trace</summary>

- intent: `pregnancy_announcement`  tags: `celebration`  language: `en`
- emotional_state: 'excited joyful'
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `announcements`
- action: `REPLY:pregnancy_announcement`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** thank you so much for everything

**Sonia:**

> It means a lot to hear that from you.
>
> You did the hard work, and I’m glad to have been part of your path. Wishing you all the best moving forward.
>

<details><summary>trace</summary>

- intent: `pregnancy_announcement`  tags: `celebration`  language: `en`
- emotional_state: 'grateful'
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `announcements`
- action: `REPLY:pregnancy_announcement`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Celebrates, no qualification, no program, no link.
- Turn 2 no longer opens with "Thank you for sharing that with me", the templated line from Appendix A.1, which is now named in both `40_voice.md` and `60_contract.md`.
