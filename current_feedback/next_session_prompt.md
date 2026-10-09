# Sonia's testing feedback: issues on our side (points 3, 4, 5, 6)

Sonia tested the brain and sent 10 points. The others are either missing from the manual or contradict it, and are going back to her. These 4 are cases where the Operating Manual v2.0 already supports what she wants, and the brain gets it wrong anyway. This file describes the feedback and the problem only. Investigate and decide the fix yourself.

Context:

- Read `CLAUDE.md` first. It covers the no-dash rule, fixing in prompts rather than Python, few-shot conventions and git etiquette.
- The live prompts are in `prompts_simple/` (`read.md`, `write.md`, `turn.md`, `safety.md`, `knowledge.md`, `language.md`). `prompts/` is not what runs.
- The source of truth is `current_feedback/The Fertility Solution DM AI Operating Manual v2.0.docx`. Do not edit it.
- The full comparison of all 10 points is in `current_feedback/feedback_vs_manual.md`.

## 3. Unprompted medical disclaimers in emotional or educational moments

Sonia's feedback:

> When someone said she was scared that low AMH meant she had missed her chance, the reply began: "I can't tell you what your AMH means for your chances; that's something to discuss with your doctor." That is not how I would respond. I would validate her fear, offer grounded encouragement and explain the general information without promising an outcome.
>
> Similarly, when someone mentioned taking metformin and feeling overwhelmed by food and supplements, the brain warned against changing medication even though she hadn't asked to change it.
>
> Please respond to what she actually says. Keep appropriate boundaries when someone requests medical decisions, but don't insert a refusal or referral into ordinary educational and emotional conversations. The tone should be empathetic, validating, encouraging and hopeful.

What the manual says:

- The boundary is real. The AI must not interpret her result or say what her AMH means for her odds (Part 1 section 3, Part 2B.2 section 5). Sonia agrees ("without promising an outcome").
- General education is allowed (Part 2B.2 section 4: "General education is appropriate."). Section J gives the AMH framing ("Your AMH is information. It is not your identity, and it is not your entire fertility story.") and says what AMH is and is not.
- The medication rules are triggered by a request ("Requests to stop medication", "The person requests medication advice", Part 2B.2 sections 10 and 13). Nothing tells the AI to warn about medication nobody asked about.
- Part 6 section 6.3: a factual question can carry an emotional concern, and the AI should answer both. Part 1 section 14 (Hope With Integrity) asks for grounded hope.

The problem:

- The boundary is applied as the opening move whenever the topic is medical, even when she has expressed fear or overwhelm rather than asked for a medical decision. Her emotion goes unanswered, and the refusal arrives before any warmth or general information.
- `prompts_simple/write.md:132` instructs "Decline in one line, say where it belongs (her doctor, or the coaching itself)". `write.md:135-137` gives an AMH example that opens with a refusal and a doctor referral, close to word for word the reply Sonia quoted.
- The metformin transcript is not in the repo, so it is unconfirmed whether the reader flagged `requested_medication` on a mention, or the writer volunteered the warning from the rule list at `write.md:125-130`. Find out which.

## 4. The brain fills in facts she never gave

Sonia's feedback:

> It repeatedly described women as "trying naturally" when they had only said they were trying to conceive. It also brought up "your partner's side" before a partner had been mentioned. Please don't fill in missing facts. The booking invitation has a specific partner rule below, but that doesn't justify assumptions throughout the conversation.

What the manual says:

- Part 1 section 3: never invent facts.
- Part 2A section 7: understanding her journey stage "creates context. It should not create assumptions."

The problem:

- `prompts_simple/read.md:51` records trying for a while with no treatment mentioned as `conceiving_mode: natural`. `read.md:57` then records trying naturally as `partner_status: partnered`. One unstated fact becomes 2, and the writer receives both as known facts.
- The writer is shown "her partner's side" as a standard thing to offer: `turn.md:48`, and the example at `write.md:234-235`. It says it regardless of whether a partner exists.
- Sonia's separate partner-at-booking rule (point 9, not in this scope) is the only place a partner may be raised unprompted.

## 5. The brain says group coaching is in Spanish

Sonia's feedback:

> It explicitly said both group and private sessions were in Spanish. This is incorrect. The rule is: group coaching is in English, private coaching is available in Spanish, core materials and videos are in English. This needs to be accurate and consistent.

What the manual says:

- Section L: "Sonia can personally coach in Spanish, but The Fertility Solution and The Pregnancy Solution materials are in English... Do not describe the full program as available in Spanish."
- Part 2A section 14 says the same. Group coaching language is not stated explicitly, but "personally coach" plus "do not describe the full program as available in Spanish" rules out what the brain said.

The problem:

- The prompt says "coaching" in Spanish without separating private from group: `prompts_simple/write.md:224` ("You coach in Spanish") and the example at `write.md:226-227` ("Puedo hacer el coaching contigo en español").
- `turn.md:111-112` tells the writer to say "you coach in Spanish". The model generalises this to all coaching, including group sessions.
- Spanish versions of the few-shots are planned later and are out of scope here. This is about the rule itself being stated accurately.

## 6. Human handoff, the silent age review, and AI disclosure

Sonia's feedback:

> The test showed the human takeover trigger, but after a follow-up acknowledgment it repeated the exact same handoff message and triggered takeover again. Please verify that takeover actually routes the conversation to the team, preserves the history and stops repetitive automated handoff messages.
>
> The age 47 test triggered age_needs_review, but the output shown had no message acknowledging the woman. Please check that she receives an appropriate response as well as the internal routing.
>
> AI disclosure also needs clearer wording. "You're talking with my AI assistant" still speaks as Sonia. It should identify itself as Sonia's AI assistant. Avoid promising someone will respond "shortly" unless that timing is supported.

What the manual says:

- Section F: the approved disclosure is "You're chatting with Sonia's AI assistant right now. I'm trained to answer questions here, support you and point you in the right direction based on Sonia's approach. If you'd prefer to speak with a human, I can bring someone from the team into the conversation. Would you like me to do that?" If she says yes, take over and keep the full context.
- Part 2B.2 section 13 (escalation): tell her the team wants to review her situation carefully. "The person should feel cared for, not transferred."
- Section E: only say the team is alerted when an alert is actually generated. Open question 4 in `prompts/manual.md` notes that nobody receives a push notification. Paused conversations wait in the dashboard queue.

The problems:

- **Repeat handoff.** In the live worker a paused lead's messages are skipped (`app/worker.py:102`). Sonia tests in the admin sandbox (`app/api/admin/router.py:132`), which is stateless server side and round-trips `lead_state` through the client. The pause does not appear to carry to the next sandbox turn, so a follow-up re-runs the brain, hits the trigger again and resends the handoff line. Verify this, and verify the live path end to end: the pause, the history preserved, no second automated message.
- **Silent age review.** `age_needs_review` (ages 46 to 48, `app/services/dossier.py:254`) has no entry in `HANDOVER_MESSAGES` (`dossier.py:62`), so the handover is silent by design and she receives nothing. Other review reasons may have the same problem. Check which ones are silent.
- **Disclosure wording.** `prompts_simple/write.md:221` and `turn.md:24` teach "my AI assistant", speaking as Sonia, instead of the section F wording.
- **"Shortly".** The seeded team handover line says "Someone will come back to you shortly." It lives in the `handover_message_team` config (seeded in `alembic/versions/r8s9t0u1v2w3_brain_v2_knowledge_base.py:134`, which must not be edited). Nothing in the system guarantees that timing.
