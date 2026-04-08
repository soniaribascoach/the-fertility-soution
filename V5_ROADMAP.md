# V5 Correction Roadmap — The Fertility Solution AI

Based on client feedback from v4 testing across 20+ real-life scenarios.

---

## Issue 1 — Memory + Conversation Continuity

**Problem:** AI re-asks questions already answered and does not reference prior details naturally.

**How to solve:**
- `app/services/router.py` → Add `known_facts: str | None` to `RouteContext`. Derive it from `prior_tags` (e.g. if ttc tag is non-default, include "Trying for: 1-2 years").
- `app/services/ai.py` → `build_context_block()`: Inject a "What you already know" block when known_facts is set, with instruction to never re-ask those facts.
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Add rule — before asking any question, check conversation history. When relevant, reference prior info naturally: "Since you've been trying for two years…", "Given your PCOS diagnosis…"

**Manual Test — `/admin/simulate`**

Send these messages in order as the same lead:
1. "Hi, I'm Sarah"
2. "I've been trying for about two years"
3. "I was recently diagnosed with PCOS"
4. "I'm 34 years old"
5. "What kind of support do you offer?"

PASS: Turn 5 reply references at least one prior fact naturally — e.g. "Since you've been trying for two years…" or "With PCOS…" — without being prompted.

FAIL: Turn 5 reply re-asks TTC duration, age, or diagnosis. Or reply treats it as a fresh conversation with no context.

---

## Issue 2 — Emotional Intelligence Too Shallow

**Problem:** Generic empathy, moves too quickly to questions or explanations in high-emotion scenarios.

**How to solve:**
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Add — "The heavier the message, the slower and deeper your response. For miscarriage, failed IVF, hopelessness, or grief — spend the FULL reply on acknowledgment. Save questions for the next turn."
- Admin config → Expand `prompt_pattern_responses` for Failed IVF, Miscarriage, Low AMH, and Hopelessness to use the multi-sentence, bubble-style format from the client sample responses.

**Manual Test — `/admin/simulate`**

Send these messages in order:
1. "I've had 3 miscarriages"
2. "And 2 IVF rounds have failed"
3. "I feel like it's never going to happen"

PASS: Turn 3 reply is pure acknowledgment — something like "I'm so, so sorry… that's a lot to carry." No advice. No question. No pivot to next steps or services.

FAIL: Reply includes a suggestion ("Have you tried…"), a question ("How long have you been trying?"), or a redirect ("I'd love to learn more about your journey").

---

## Issue 3 — Responses Too Dense

**Problem:** One compact paragraph instead of natural conversational pacing / multiple bubbles.

**How to solve:**
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Replace "1–4 sentences" rule with — "Write in short message bubbles separated by a blank line (two newlines). Each bubble is 1–2 sentences. Use 2–3 bubbles for normal messages, 3–4 for heavy emotional ones. Never write a single long paragraph."
- `app/services/webhook.py` (or service layer): Split `result.reply` on `\n\n` and call `send_text_message()` once per bubble, sequentially.

**Manual Test — `/admin/simulate`**

Send 5 varied messages as separate conversations:
1. "I'm just starting to think about having a baby"
2. "I was just diagnosed with endometriosis"
3. "Can you tell me about your program?"
4. "I'd love to book a call"
5. "I feel completely hopeless about all of this"

PASS: Each reply arrives as 2–3 short separate bubbles in ManyChat (or contains visible blank-line breaks in the simulate preview). Each bubble is 1–2 sentences.

FAIL: Reply is one long unbroken paragraph. Or only a single sentence with no break.

---

## Issue 4 — Over-Literal Mirroring

**Problem:** AI repeats user's exact words back, feels robotic.

**How to solve:**
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Add — "When reflecting what the user said, capture the *feeling and meaning*, not their exact words. Paraphrase with warmth. Never repeat a user's phrase back verbatim."

**Manual Test — `/admin/simulate`**

Send: "I feel like my body is betraying me"

PASS: Reply captures the emotional weight without echoing the phrase. Example: "That feeling of your own body working against you is really painful" — or something entirely different that still honours the emotion.

FAIL: Reply contains the phrase "body is betraying you" (or "body is betraying me") verbatim, or any close literal echo.

---

## Issue 5 — Generic Openers + Conversation Resets

**Problem:** "Hi, I saw your message" / "Hi, I'm glad you reached out" used mid-conversation, treating each turn as a fresh start.

**How to solve:**
- Admin config → Update `prompt_opening_variants` to remove/replace generic variants with direct, warm openers:
  - "What's been going on for you lately?"
  - "Tell me a little about your journey so far."
  - "I'd love to hear what's brought you here."
  - "What's been on your mind around this?"
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Add — "Never open a reply mid-conversation with 'Hi', 'Hey', 'Hello', 'I saw your message', 'I'm glad you reached out', or any greeting-style phrase. Respond directly to what was just said."

**Manual Test — `/admin/simulate`**

Send a 3-turn history first:
1. "Hi, I've been trying to conceive for 18 months"
2. "I have unexplained infertility"
3. "My doctor is recommending IVF"

Then send a 4th message: "I'm just not sure if I'm ready for that"

PASS: Turn 4 reply opens directly with a response to what was just said. No "Hi", "Hey", "I saw your message", "I'm so glad you reached out", "I'm glad you're here."

FAIL: Reply opens with any greeting phrase. Reply treats turn 4 as if it's turn 1.

---

## Issue 6 — Too Many Questions

**Problem:** Qualification question injected every turn regardless of emotional context — stacks on top of heavy moments.

**How to solve:**
- `app/services/router.py` → Add `suppress_question: bool` to `RouteContext`. Set to True when `matched_pattern` label contains any of: ["miscarriage", "ivf", "hopeless", "grief", "amh"].
- `app/services/ai.py` → `build_context_block()`: Skip question injection when `route.suppress_question` is True.

**Manual Test — `/admin/simulate`**

Send 5 varied messages across separate conversations:
1. "Tell me about your coaching program"
2. "I've been trying to conceive for a year"
3. "I had a miscarriage last month"
4. "My IVF failed for the second time"
5. "I feel like nothing is working"

PASS: Each reply contains at most one question mark. Replies to messages 3, 4, and 5 contain zero question marks.

FAIL: Any reply contains two or more questions. A reply to a miscarriage or IVF failure ends with a qualifying question.

---

## Issue 7 — No Emotional Progression

**Problem:** Conversation does not deepen over time — same acknowledgment depth on turn 1 and turn 8.

**How to solve:**
- Admin config → `prompt_flow`: Add — "As the conversation progresses, increase emotional depth and specificity. Turn 1–2: acknowledge and invite. Turn 3–4: reflect and connect. Turn 5+: offer insight and gentle direction. The conversation should feel like it is going somewhere."

**Manual Test — `/admin/simulate`**

Send this escalating 6-turn conversation:
1. "Hi, I'd like to learn more about fertility coaching"
2. "I've been trying for two years"
3. "I was diagnosed with low AMH last year"
4. "I've done 3 IUIs — none worked"
5. "I'm completely exhausted by all of it"
6. "I just feel so stuck"

PASS: Turn 6 reply is noticeably more specific and emotionally resonant than a turn-1 reply would be. It references the arc — the years of trying, the diagnosis, the failed treatments — not just the word "stuck."

FAIL: Turn 6 reply could have been sent on turn 1. Generic acknowledgment with no reference to the journey shared.

---

## Issue 8 — No Narrative Building

**Problem:** AI treats each data point in isolation instead of synthesizing them into a coherent picture of the person.

**How to solve:**
- Admin config → `prompt_flow`: Add — "When a person has shared multiple data points (age, TTC duration, diagnosis, treatment history), synthesize them into one coherent picture before offering insight. Say something like 'What I'm hearing is…' or 'Putting this together…'. This is not a checklist — it is a person's story."

**Manual Test — `/admin/simulate`**

Send these messages in order:
1. "I'm 37"
2. "I've been trying for two years"
3. "I have PCOS"
4. "I did one IUI and it didn't work"
5. "I don't know what to do next"

PASS: Turn 5 reply synthesises at least two of the prior facts into a coherent picture. Something like "Putting this together — two years of trying, PCOS, and a failed IUI at 37 — what I'm hearing is someone who has been working really hard with no clear answer yet."

FAIL: Turn 5 reply responds to "I don't know what to do next" in isolation with no reference to the context that was shared.

---

## Issue 9 — Explains Too Early

**Problem:** AI jumps into education or clinical context before emotional connection is established.

**How to solve:**
- Admin config → `prompt_flow`: Add — "Do not explain, educate, or give medical information in the first 2 turns. The first priority is connection. Once you have acknowledged and asked one meaningful question, you may offer a light reframe. Connection before guidance. Guidance before education."

**Manual Test — `/admin/simulate`**

Start a fresh conversation. Send as the very first message:
> "I have PCOS and low AMH."

PASS: Reply acknowledges emotionally and asks one meaningful question. No explanation of what PCOS is. No AMH statistics. No mention of protocols or next steps.

FAIL: Reply explains what PCOS or low AMH means, gives a statistic, offers a protocol, or pivots to what the program can do for them.

---

## Issue 10 — Conversion Flow Needs Refinement

**Problem:**
- High-intent: booking link fires abruptly — no warm build-up.
- Low-intent: no mechanism to identify and redirect early.

**How to solve:**
- `app/services/ai.py` → `booking_fires_now_instruction()`: Replace current instruction with structured 5-step sequence:
  1. Acknowledge what they've shared (1 sentence)
  2. Frame the next step naturally ("The best next step is…")
  3. Explain the value of the call — clarity, not a sales pitch (1 sentence)
  4. Soft buy-in ask ("Does that feel like a good next step for you?")
  5. Share the link naturally
- `app/services/router.py` → `_run_classifier()`: Add `low_intent: bool` to classifier output. When true, inject instruction to gently ask what brought them here personally before continuing.

**Manual Test — `/admin/simulate` (High-Intent)**

Build a conversation to booking threshold (or manually set `booking_fires_now=True` in the route context for testing). Then send: "I think I'm ready to take the next step."

PASS: Reply follows the 5-step arc naturally — acknowledges → frames next step → explains value briefly → asks soft buy-in → shares the link. Feels warm and personal, not like a script.

FAIL: Link appears in the first or second sentence with no build-up. Reply sounds like a sales pitch. Reply says "someone will reach out" instead of providing the link.

**Manual Test — Low-Intent**

Start a fresh conversation and send: "I just wanted to see what this is all about"

PASS: Reply gently asks what brought them here personally before continuing — e.g. "Of course — what's been going on for you lately?" No immediate qualification or pitch.

FAIL: Reply launches into a description of services. Or immediately asks qualifying questions about TTC duration.

---

## Issue 11 — Scoring Does Not Reflect Emotional Signals

**Problem:** Emotional statements of desperation or hopelessness don't map to higher urgency/readiness tags — may actually decrease score.

**How to solve:**
- `app/services/ai.py` → `TAGGING_INSTRUCTIONS`: Add explicit mappings:
  - "I feel like it will never happen", "I've tried everything", "I give up" → `urgency_high`
  - "Doctor says IVF is my only option", "recommended donor eggs" → `urgency_high` + `diagnosis_confirmed`
  - "I'm ready to try something different", "I want to do whatever it takes" → `readiness_considering` or `readiness_ready`
  - Statements of hopelessness or desperation → INCREASE urgency, never decrease
- Admin config → `prompt_scoring_rules`: Add all of the above as business-defined signals.

**Manual Test — Admin panel or DB**

Send these as 3 separate fresh conversations and check the tags saved for each lead:

1. > "I feel like it's never going to happen"
   PASS: `urgency = urgency_high`
   FAIL: `urgency_low` or `urgency_medium`

2. > "My doctor says IVF is my only option at this point"
   PASS: `urgency = urgency_high` AND `diagnosis = diagnosis_confirmed` or `diagnosis_suspected`
   FAIL: `urgency_low` or `diagnosis_none`

3. > "I've tried everything and nothing works"
   PASS: `urgency = urgency_high`
   FAIL: `urgency_low` or `urgency_medium`

Check tags in the admin lead detail view or directly in the conversations table after each exchange.

---

## Issue 12 — Missing Strategic Positioning

**Problem:** Pattern responses are single-line and cover only 4 scenarios. Several key triggers have no messaging at all.

**How to solve:**
- Admin config → `prompt_pattern_responses`: Expand to cover all key triggers with 3–4 sentence responses in bubble style:

| Trigger | Core reframe |
|---------|-------------|
| Low AMH | Low AMH ≠ no baby. Quality > quantity. |
| IVF pressure / only option | IVF isn't the only path. What hasn't been fully supported yet? |
| Unexplained infertility | Normal tests ≠ no answers. We just haven't looked deeply enough. |
| Failed IVF / IUI | The environment wasn't fully supported yet — not a body failure. |
| Donor egg pressure | You deserve to feel empowered, not just handed a protocol. |
| PCOS | Help the body feel safe enough to regulate. Not just about ovulation. |
| Endometriosis | Root cause, not symptom management. |
| POI | Not the end of the story. Whole-body perspective matters. |
| Irregular cycles | The body communicates through cycles. Listen, don't override. |
| Perimenopause / age concern | Age is one factor. Not the full picture. |
| Recurrent miscarriage | Three losses means something deeper needs to be heard. |

**Manual Test — `/admin/simulate`**

Send one message per scenario in separate fresh conversations:

1. > "My AMH is really low"
   PASS: Reply includes the reframe — low AMH does not mean no baby / quality over quantity.

2. > "My doctor is pushing me toward IVF and says it's my only option"
   PASS: Reply opens alternative perspective — IVF isn't the only path / what hasn't been supported yet.

3. > "All my tests came back normal but I still can't get pregnant"
   PASS: Reply frames unexplained as "we haven't looked deeply enough" — not "normal is good news."

4. > "My IVF failed again"
   PASS: Reply frames it as the environment not being fully supported — not a body failure.

5. > "They're recommending donor eggs and I don't know how to feel about that"
   PASS: Reply focuses on empowerment — you deserve to feel in control of this decision, not just handed a protocol.

FAIL (all): Reply is generic empathy with no strategic reframe. Reply mirrors what the doctor said without pushing back.

---

## Issue 13 — Tone Needs More Human Texture

**Problem:** Language is too polished. Sounds like a trained assistant, not a human who genuinely cares.

**How to solve:**
- Admin config → `prompt_tone`: Replace current examples with raw, natural-style phrases:
  - "I'm so, so sorry…" (not "I'm sorry to hear that")
  - "That's a lot to carry" (not "That sounds difficult")
  - "That must feel really heavy"
  - "You shouldn't have to hold this alone"
- `app/services/ai.py` → `PLAIN_TEXT_INSTRUCTIONS`: Add — "Use natural, slightly imperfect language. It's okay to say 'I'm so, so sorry' or 'That's a lot…'. Don't over-polish. Write like a human who genuinely cares."

**Manual Test — `/admin/simulate`**

Send these as 3 separate fresh conversations:

1. > "I just had a miscarriage"
2. > "My IVF failed for the second time"
3. > "I feel completely hopeless about ever getting pregnant"

PASS: Replies contain natural, warm, slightly imperfect language. Examples of passing phrases: "I'm so, so sorry…", "That's a lot to carry", "That must feel really heavy", "You shouldn't have to hold this alone."

FAIL: Replies sound polished and clinical. Examples of failing phrases: "I'm sorry to hear that", "That sounds very difficult", "I understand how you must be feeling", "I appreciate you sharing that with me."

---

## Execution Order

| # | Change | Type | Files |
|---|--------|------|-------|
| 1 | No-generic-opener + no-mirroring + memory rules in `PLAIN_TEXT_INSTRUCTIONS` | Code | `ai.py` |
| 2 | Emotional pacing + emotional signal → tag mappings in `TAGGING_INSTRUCTIONS` | Code | `ai.py` |
| 3 | Booking instruction 5-step structure | Code | `ai.py` |
| 4 | Known facts summary in `RouteContext` + `build_context_block` | Code | `ai.py`, `router.py` |
| 5 | Question suppression for high-emotion turns | Code | `router.py` |
| 6 | Multi-bubble reply splitting | Code | `webhook.py` |
| 7 | All config updates (opening variants, tone, flow, pattern responses, scoring rules) | Config | Admin panel |

---

## V5 Manual Test Checklist

Run all tests via `/admin/simulate` after implementation. Check off each when it passes.

- [ ] **Issue 1 — Memory:** 5-turn conversation, turn 5 references prior facts without being asked
- [ ] **Issue 2 — Emotional depth:** 3-message grief escalation, final reply is pure acknowledgment — no questions, no pivot
- [ ] **Issue 3 — Bubbles:** 5 varied messages, each reply arrives as 2–3 separate short bubbles
- [ ] **Issue 4 — No mirroring:** "I feel like my body is betraying me" → reply does not echo the phrase
- [ ] **Issue 5 — No resets:** 3-turn history + turn 4 → reply does not open with a greeting phrase
- [ ] **Issue 6 — One question max:** 5 messages, no reply has 2+ questions; high-emotion replies have zero
- [ ] **Issue 7 — Emotional progression:** 6-turn escalation, final reply references the full arc
- [ ] **Issue 8 — Narrative synthesis:** 4 data points shared, turn 5 weaves at least two into a coherent picture
- [ ] **Issue 9 — No early explanation:** "I have PCOS and low AMH" as turn 1 → no clinical explanation
- [ ] **Issue 10 — Booking flow:** booking trigger → 5-step arc; low-intent opener → gentle redirect before qualification
- [ ] **Issue 11 — Urgency tagging:** 3 desperation messages → all produce `urgency_high` in admin tags
- [ ] **Issue 12 — Strategic positioning:** 5 scenario messages → each reply contains the correct reframe
- [ ] **Issue 13 — Human tone:** 3 grief messages → replies use warm, natural language, not polished corporate empathy
