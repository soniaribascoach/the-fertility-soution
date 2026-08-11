# r2_25_already_pregnant: Already pregnant, wants coaching to hold the pregnancy

**What the manual requires:** She is pregnant, so she is a pregnancy announcement however frightened she sounds. Congratulate her and wish her well. Every case in §3 is pre-conception, so say plainly that coaching through a pregnancy is not what this is and leave her with her medical team. No qualification, no coaching, no food list.

**Manual references:** 2A step 1 (a pregnancy announcement is celebrated), 2B.1 §2, §3 (program scope)

_Run 2026-08-11 15:17 UTC, 2 turns, $0.015234_

---

### Turn 1

**Lead:** i'm 7 weeks after 3 losses and terrified. can you coach me through this pregnancy?

**Sonia:**

> Congratulations on your pregnancy. Seven weeks is an important milestone, and I understand how frightening this must feel.
>
> I don’t coach through pregnancy itself because my work focuses on preparing the body to conceive and supporting fertility before pregnancy. Now you are in the care of your medical team, and that is exactly where you need to be.
>
> I hope this pregnancy goes well for you. I’m glad you reached out to share this.
>

<details><summary>trace</summary>

- intent: `pregnancy_announcement`  tags: `celebration`  language: `en`
- explicit_question: 'can you coach me through this pregnancy?'
- emotional_state: 'terrified'
- slots: `{"miscarriage_history": "3 losses", "pregnancy_priority": "high"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `announcements`
- action: `REPLY:pregnancy_announcement`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** just tell me what to eat and what to avoid so i don't lose this one too

**Sonia:**

> I’m not going to give you a list, because there isn’t one that can prevent loss.
>
> If there were specific foods you had to eat or avoid to keep a pregnancy, every woman who has experienced loss would have been given that list already.
>
> What happened before this pregnancy was not caused by something you ate or didn’t eat.
>

<details><summary>trace</summary>

- intent: `pregnancy_announcement`  tags: `celebration, free_coaching, recurrent_loss`  language: `en`
- explicit_question: "just tell me what to eat and what to avoid so i don't lose this one too"
- emotional_state: 'terrified'
- slots: `{"miscarriage_history": "3 losses", "goal_stated": "don't lose this one"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `announcements, education_spiral, free_coaching_request`
- action: `REPLY:pregnancy_announcement`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Turn 1 congratulates her first, then says plainly that coaching through a pregnancy is not what this is because the work is the part before conception, then leaves her with her medical team and wishes her well. That is 2A step 1 (a pregnancy announcement is celebrated) and 2B.1 §3, whose scope list is pre-conception from top to bottom.
- Turn 2 gives no food list and does not slide into one after refusing.
- This took three tries and each one taught something. Round 3 invented a policy refusing pregnancy support; the first attempt this round invented one providing it; the second got the scope right and forgot to congratulate her. The model was not defending a position, it was filling a silence in whichever direction the conversation leaned.
- The reader is what fixed it. She is now read as `pregnancy_announcement` by the fact that she is pregnant rather than by her tone, and the intent sticks for the rest of the conversation, so turn 2 is answered by the announcements conversation rather than by the fresh-grief one.
