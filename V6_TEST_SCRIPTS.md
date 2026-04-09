# V6 Manual Test Scripts — /admin/simulate

Run each test in a **fresh simulate session** unless stated otherwise. Check off each when it passes.

---

## Test 1 — CTA Two-Step: Buy-In First, Link After Confirmation

**What we're testing:** Score hits threshold → AI asks buy-in question (no link). User says yes → link fires.

**Setup:** Make sure a booking link is configured in admin config. Set score threshold low (e.g. 20) temporarily if needed, or build up a qualifying conversation naturally.

**Step 1 — Build a qualifying conversation (same session):**

Send these in order:
1. "I'm 38 and I've been trying to conceive for two and a half years"
2. "I was diagnosed with low AMH last year"
3. "I've done two rounds of IVF and neither worked"
4. "I feel like I'm running out of time and options"
5. "I'm really ready to try something different, whatever it takes"

**Step 2 — Check response to message 5 (or whichever hits threshold):**

PASS: Reply asks a soft buy-in question — e.g. "Does that feel like a good next step for you?" No URL appears anywhere in the message.

FAIL: Booking URL appears in this reply. Or no buy-in question is asked despite score being high.

**Step 3 — Reply positively (same session):**

Send: "Yes, that sounds good"

PASS: Booking link appears in this reply, naturally woven in (e.g. "You can grab a time here: [url]").

FAIL: Link does not appear. Or link appeared in step 2 already.

**Step 4 — Reply again (same session):**

Send: "Amazing, thank you"

PASS: Normal conversational reply — no second link sent.

FAIL: Link appears again.

---

## Test 2 — No Therapy Language

**What we're testing:** Banned phrases ("what I'm hearing is...", "that must feel...", "I can hear that...") never appear.

Run each as a separate fresh session.

Send: "I feel like my body is broken and I'm running out of hope"

PASS: Reply acknowledges with warmth but uses natural language. No: "what I'm hearing is...", "that must feel...", "I can hear that...", "I understand how you must be feeling", "I appreciate you sharing that."

Send: "My third IVF just failed"

PASS: Same — warm, direct, no scripted empathy phrases. Reply is pure acknowledgment, no question, no pivot.

Send: "All my tests came back normal but I still can't get pregnant"

PASS: Reply offers a reframe ("normal doesn't mean optimal / we just haven't looked deeply enough") — not just empathy.

---

## Test 3 — Expert Voice and Practical Value

**What we're testing:** Replies include insight, reframe, or guidance — not just emotional mirroring.

Run each as a separate fresh session.

**3a — Low AMH**

Send: "My AMH came back really low and my doctor said it's not looking good"

PASS: Reply includes the reframe — low AMH is about quantity not quality, low AMH does not mean no pregnancy. Calm and certain, not alarmed.

FAIL: Reply is pure empathy with no reframe or insight.

**3b — IVF as only option**

Send: "My doctor is saying IVF is my only option at this point"

PASS: Reply opens an alternative perspective — IVF is a tool, not the only path. Asks what hasn't been fully supported yet.

FAIL: Reply agrees with the doctor or just mirrors the user's anxiety.

**3c — Unexplained infertility**

Send: "All my tests came back normal but I still can't get pregnant after 18 months"

PASS: Reply frames this as "normal tests don't mean no answers, we just haven't looked deeply enough." Not dismissive, not clinical.

FAIL: Reply says "normal results are actually good news" or offers no reframe.

**3d — LH strips / ovulation**

Send: "I've been using LH strips every month but I'm not sure I'm timing it right"

PASS: Reply offers a small practical insight — e.g. common mistake is testing too late in the day or starting too early in the cycle. Feels like expert knowledge, not a Google answer.

FAIL: Reply just validates the effort with no micro-value.

**3e — Ovulation / cycle patterns**

Send: "My cycles are really irregular, sometimes 35 days sometimes 45"

PASS: Reply offers a light insight about what irregular cycles may signal (the body communicating something, not just a timing problem). Guides toward understanding rather than just tracking.

---

## Test 4 — Personalization / Memory

**What we're testing:** AI naturally references prior facts without being re-asked.

Run as a single session, sending in order:

1. "Hi, I'm Sarah"
2. "I'm 36"
3. "I've been trying for about two years"
4. "I was recently told my AMH is low"
5. "I've also done one round of IVF that didn't work"
6. "What kind of support do you actually offer?"

PASS on turn 6: Reply references at least two prior facts naturally — e.g. age, TTC duration, AMH, or IVF. Does not re-ask anything already shared. Does not treat this as a fresh conversation.

FAIL: Reply re-asks how long they've been trying, or ignores all prior context and just describes services generically.

---

## Test 5 — No Early Explanation (Connection Before Education)

**What we're testing:** AI does not jump into clinical information on turn 1 or 2.

Start a fresh session. Send as the very first message:

"I have PCOS and low AMH"

PASS: Reply acknowledges emotionally and asks one meaningful question. No explanation of what PCOS is. No AMH statistics. No protocol suggestions. No mention of services.

FAIL: Reply explains PCOS or AMH, gives numbers, offers a protocol, or pivots to the program.

---

## Test 6 — One Question Max / Emotional Suppression

**What we're testing:** High-emotion replies contain zero questions. All replies contain at most one.

Run each as a separate fresh session.

Send: "I just had a miscarriage last week"

PASS: Reply is pure acknowledgment. Zero question marks. No pivot, no advice, no next steps.

Send: "My IVF failed for the second time"

PASS: Same. Pure acknowledgment only. Zero question marks.

Send: "I feel completely hopeless about ever getting pregnant"

PASS: Same.

Send: "Can you tell me more about how your program works?"

PASS: Reply answers and asks at most one follow-up question. Not two.

---

## Test 7 — No Generic Openers Mid-Conversation

**What we're testing:** AI never opens a mid-conversation reply with a greeting phrase.

Run as a single session:

1. "Hi, I've been trying to conceive for 18 months"
2. "I have unexplained infertility"
3. "My doctor is recommending IVF"
4. "I'm just not sure if I'm ready for that"

PASS on turn 4: Reply opens directly with a response to the content. No "Hi", "Hey", "I saw your message", "I'm so glad you reached out", "I'm glad you're here."

FAIL: Any greeting phrase appears at the start of turn 4.

---

## Test 8 — Conversation Deepens Over Time

**What we're testing:** Reply at turn 6 is noticeably more specific and emotionally resonant than turn 1 would be.

Run as a single session:

1. "Hi, I'd like to learn more about fertility coaching"
2. "I've been trying for two years"
3. "I was diagnosed with low AMH last year"
4. "I've done 3 IUIs — none worked"
5. "I'm completely exhausted by all of it"
6. "I just feel so stuck"

PASS on turn 6: Reply references the arc — the years of trying, the diagnosis, the failed IUIs — not just the word "stuck." Noticeably more specific than a turn-1 reply would be.

FAIL: Turn 6 reply could have been sent on turn 1. Generic acknowledgment, no reference to what was shared.

---

## Quick Smoke Test (Run All 5 in One Pass)

If you want a fast sanity check across the main scenarios, run these 5 as separate fresh sessions:

1. "My AMH is really low" → expect: low AMH reframe, calm certainty
2. "I just had a miscarriage" → expect: pure acknowledgment, no question, no pivot
3. "I feel like it's never going to happen" → expect: warm acknowledgment, no therapy phrases
4. "I've been trying for two years and I'm 37" → then send "what support do you offer?" → expect: references age + TTC in reply
5. Build a 5-turn qualifying conversation → expect: buy-in question without a link, then link only after "yes"
