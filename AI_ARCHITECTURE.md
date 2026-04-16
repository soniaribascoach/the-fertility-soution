# AI Pipeline Architecture — The Fertility Solution

**Version:** v7 (proposed redesign)  
**Status:** Design — pending implementation  
**Supersedes:** v6 monolithic prompt architecture

---

## Why This Exists

The v6 system builds a single 600+ word system prompt and asks one LLM call to simultaneously: write empathetically, insert authority, handle pricing, ask the right qualification question, structure bubbles correctly, avoid forbidden phrases, never repeat itself, track all known facts, AND classify five tagging dimensions across the conversation.

The model fails under that cognitive load. The result: hallucinations, therapy-speak, wrong bubble counts, re-asked questions, and inconsistent voice.

The redesign decomposes each of those concerns into single-purpose steps. Each step has one job. The orchestrator decides strategy. The writer only writes. The tagger only tags. A quality gate catches rule violations before they reach the user.

---

## Full Pipeline

```
Incoming User Message
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1 — SAFETY GATE                         (no LLM)        │
│                                                                  │
│  medical_blocklist match → send deflection message, stop        │
│  human_takeover match   → handoff message, tag, stop            │
└─────────────────────────────────────────────────────────────────┘
        │  (only continues if safe)
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2 — CONTEXT AGENT                   (1 cheap LLM call)  │
│                                                                  │
│  Input:  last 6 turns + current message                         │
│  Output: {                                                       │
│    emotion:           "neutral" | "mild_distress" | "grief"     │
│    scenario_idx:      int  (-1 = none matched)                  │
│    objection_idx:     int  (-1 = none matched)                  │
│    authority_useful:  bool                                      │
│    low_intent:        bool                                      │
│  }                                                               │
│                                                                  │
│  "grief" = miscarriage, IVF/IUI failure, devastated,            │
│            hopelessness, recurrent loss, donor egg pressure      │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3 — STRATEGY ENGINE                      (no LLM)       │
│                                                                  │
│  Inputs:  context output + prior_tags + score + turn number     │
│           + booking flags + price flags + cfg                   │
│                                                                  │
│  Produces TurnDirective:                                        │
│    goal:            see Goal Table below                        │
│    bubble_count:    1 | 2 | 3                                   │
│    question:        str | None  (one qualification question)    │
│    authority_phrase: str | None                                 │
│    cta_line:        str | None                                  │
│    booking_phase:   "none" | "ask" | "send"                     │
│    booking_url:     str                                         │
│    suppress_question: bool                                      │
│    turn_number:     int  (for turn-aware tone modulation)       │
│    known_facts:     str  (synthesised from tags + history)      │
│    writer_brief:    str  (specific 15–20 line instruction)      │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─────────────────────────────────────────────────────────┐
        │  (parallel)                                             │
        ▼                                                         ▼
┌───────────────────────────┐               ┌─────────────────────────────┐
│  STAGE 4A — WRITER        │               │  STAGE 4B — TAGGER          │
│  (main LLM call)          │               │  (cheap parallel LLM call)  │
│                           │               │                             │
│  System prompt (~120 words):              │  Input: full conversation   │
│  - Sonia persona (5 lines)│               │  Output: JSON tags only     │
│  - Voice rules (8 lines)  │               │    {ttc, diagnosis, urgency, │
│  - cfg.prompt_hard_rules  │               │     readiness, fit}         │
│  - writer_brief           │               │                             │
│                           │               │  Completely separate task   │
│  Output: reply text only  │               │  so writer isn't split-     │
│  No tags. Just write well.│               │  tasking on two jobs        │
└───────────────────────────┘               └─────────────────────────────┘
        │                                                         │
        ▼                                                         │
┌─────────────────────────────────────────────────────────────────┤
│  STAGE 5 — QUALITY GATE              (cheap LLM, ~50 tok out)  │
│                                                                  │
│  Checks reply for hard rule violations:                         │
│  1. Em-dash (—) → replace with comma or split sentence          │
│  2. More than one question → keep the most important, drop rest │
│  3. Therapy phrases → rewrite that sentence                     │
│     ("what I'm hearing is", "that must feel", "that sounds      │
│      difficult", "I appreciate you sharing")                    │
│  4. Re-asks a known fact → remove that question                 │
│  5. Wrong bubble count vs directive → restructure               │
│  6. Repeated opener from prior turns → rephrase opening         │
│                                                                  │
│  Output: corrected reply (or original if clean)                 │
└─────────────────────────────────────────────────────────────────┘
        │                                             │
        └─────────────────────────────────────────────┘
                             │  merge
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 6 — ASSEMBLER                            (no LLM)       │
│                                                                  │
│  compute_score(tags) → new_score                                │
│  persist: user message, assistant reply, tags, score, flags     │
│  split reply on \n\n → bubbles list                             │
│  ── ManyChat / production: ──                                    │
│    for each bubble: calculate send_delay, wait, deliver          │
│  ── Simulate: ──                                                 │
│    return {reply, bubbles, tags, score, cost, flags...}          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Goal Table (Stage 3 Strategy Engine)

| Goal | Trigger condition | Bubble count | Key behaviour |
|------|-------------------|--------------|---------------|
| `open` | is_first + user said hi/nothing | 2 | Warm greeting + opening_variant |
| `open_context` | is_first + user already shared context | 2 | Brief greeting + respond to what they said, no opening_variant |
| `empathize` | emotion == grief | 2 | Pure ack + soft invitation. No question. No services. |
| `empathize_qualify` | emotion == mild_distress | 2 | Ack + gentle question OK |
| `low_intent` | low_intent == True | 1 | "What brought you here?" — nothing else |
| `handle_pricing_deflect` | pricing detected, first ask | 2 | Redirect to zoom. No range. End with soft booking question. |
| `handle_pricing_reveal` | pricing detected, second ask + score > 50 | 2 | Share range from cfg.prompt_pricing. Value prop. Soft booking Q. |
| `handle_pricing_redirect` | pricing detected, second ask + score ≤ 50 | 2 | Continue redirect. No range. |
| `handle_objection` | objection_idx matched | 2 | Use objection guidance, adapt naturally |
| `educate` | scenario_idx matched | 1–2 | Ack + one insight/reframe from pattern. No booking mention unless already in sequence. |
| `synthesise` | turn ≥ 5 + ≥ 3 known data points | 2 | Connect the dots: "Putting this together..." |
| `confirm_booking` | booking_phase == ask | 2–3 | Plant the seed. Soft "does that feel right?" No URL. |
| `send_booking` | booking_phase == send | 3 | Ack + value + URL. Exactly 3 bubbles. |
| `nurture` | score ≥ 75% of threshold, no booking yet | 2 | cta_line woven in naturally |
| `qualify` | default | 1–2 | Ack + insight/reframe + one qualification question |

---

## Writer Brief Specification

The `writer_brief` is the key innovation. It replaces `build_context_block()`. Instead of a 40+ line wall of conditional instructions, the strategy engine assembles a SHORT, turn-specific directive (15–20 lines max).

Every writer brief includes:
1. What was just said / what emotional context to acknowledge
2. What the goal for this turn is
3. Specific content to include (question, authority, CTA, URL)
4. What NOT to do this turn
5. Bubble count and structure

### Example briefs by goal

**goal = `empathize` (grief turn):**
```
She just told you her second miscarriage. Write exactly 2 bubbles.

Bubble 1: Real acknowledgment. 1-2 sentences. Short and honest.
No therapy phrases. No "that must feel". Just be present with the weight of it.

Bubble 2: A soft invitation to keep sharing. NOT a qualifying question.
NOT advice. Something like "I'd love to hear more about where you're at."

No question. No mention of services, zoom sessions, or next steps.
```

**goal = `qualify` (normal turn, turn 3):**
```
She's been sharing about unexplained infertility. Turns 1-2 established connection.
Now it's time to gently learn more while adding value.
What you already know — do NOT re-ask: [known_facts]

Write 1-2 bubbles:
Bubble 1: Brief acknowledgment + one small reframe or insight about unexplained infertility.
(See pattern: [scenario_text])
Bubble 2 (or weave into 1): Naturally ask: "[question_text]"

Add at least one of: a reframe, a small insight, or directional guidance.
```

**goal = `synthesise` (turn 5+, multiple data points known):**
```
She has shared enough for a synthesis. Connect the dots.

Write 2 bubbles:
Bubble 1: "Putting this together..." — link her [ttc duration], [diagnosis], [treatment history].
Show you have been listening. This should feel like insight, not a summary.
Bubble 2: One forward-looking thought or gentle question about what she wants next.

Known facts: [known_facts]
```

**goal = `handle_pricing_deflect` (first pricing ask):**
```
She asked about pricing. Write 2 bubbles.

Bubble 1: Acknowledge warmly. Explain programs vary by level of support and personalisation.
The zoom session is where we understand her situation and find the right fit — not a sales pitch.
Do NOT share any number or range.

Bubble 2: Soft question: "Would that feel like a good next step for you?"
```

**goal = `handle_pricing_reveal` (second ask, high-score):**
```
She's asking about price again and is clearly serious.
Write 2 bubbles.

Bubble 1: [range from cfg.prompt_pricing — e.g. "$1,500 to $14,000 depending on level of support"]
Immediately follow with: "we first need to understand your situation before recommending anything."
Tone: open, grounded, confident — not defensive.

Bubble 2: Soft booking question — one sentence.
```

**goal = `send_booking`:**
```
She confirmed she wants a zoom session. Write exactly 3 bubbles.

Bubble 1: Brief warm acknowledgment. Specific to what she shared.
Bubble 2: One sentence on what the session will give her — clarity, a real plan.
Bubble 3: "You can grab a time here: [url]"

No "someone will reach out". No delays implied.
```

---

## Turn-Aware Tone Modulation

The strategy engine adjusts the writer brief tone based on turn number, per the behavioural spec:

| Turn range | Tone instruction added to brief |
|------------|----------------------------------|
| 1–2 | "Connection only. No education. No clinical information. Acknowledge and invite more." |
| 3–4 | "Reflect what's been shared. You may offer one light reframe now that connection is established." |
| 5+ | "Offer insight and gentle direction. The conversation should begin to feel like it is going somewhere." |

---

## Additional Improvements Over v6

### 1. Expert Voice Enforcement (per client feedback)

The writer brief always includes: **"Add at least one of: a reframe, a small insight, or directional guidance. Every reply must guide, not just mirror."**

This addresses the #1 client complaint: "too reflective, not directive enough."

### 2. Separated Tagging (Stage 4B)

Tags are classified in a separate parallel call. In v6, the writer had to simultaneously produce a great reply AND correctly fill 5 classification fields in JSON. Separating these tasks improves quality of both. The writer can focus entirely on writing well.

### 3. Quality Gate (Stage 5)

A cheap reviewer pass catches the most common failures before they reach the user:
- Em-dash usage (hard rule)
- Multiple questions in one reply
- Therapy phrase patterns
- Re-asking known facts
- Wrong bubble count

In v6, these rules were instructions the writer was expected to self-enforce — unreliable.

### 4. Synthesis Turn (new goal)

From turn 5 onward, when ≥ 3 data points are known (age, ttc, diagnosis, treatments), the strategy engine triggers a `synthesise` goal. This produces the "Putting this together..." replies that show genuine listening and build trust — a pattern explicitly called out in the behavioural spec but missing from v6.

### 5. Anti-Repetition Context

The quality gate is given the last 3 openers/phrases used in the conversation so it can detect opener repetition. In v6, the rule "never start two replies the same way" was a prompt instruction with no enforcement.

### 6. Pricing Range Decoupled from Writer

In v6, the pricing range was buried in the writer's system prompt via `cfg.prompt_pricing`. The strategy engine now:
1. Extracts the range from `cfg.prompt_pricing` at routing time
2. Injects it explicitly into the writer brief only when `handle_pricing_reveal` fires

The writer is not expected to find and parse pricing guidance from a long blob — it receives a clear directive.

### 7. First-Message Content Detection

The strategy engine now distinguishes:
- `open` — user greeted without context → use opening_variant
- `open_context` — user's first message already contains context (diagnosis, timeline, pain) → skip opening_variant, respond directly to what they said

In v6, the opening_variant was always injected on turn 0, sometimes producing awkward responses when the user had already shared a full situation.

### 8. Response Delay / Human Typing Simulation

Client feedback item #8 (marked critical): responses arriving instantly breaks trust.

The Assembler stage (Stage 6) calculates send delay per bubble based on word count:

| Bubble length | Base delay | Randomisation |
|---------------|------------|---------------|
| Short (< 15 words) | 2–3 seconds | ± 0.5s |
| Medium (15–30 words) | 4–6 seconds | ± 1s |
| Long (> 30 words) | 6–8 seconds | ± 1.5s |

Applies only to ManyChat delivery (webhook.py), not to the simulate endpoint.

### 9. Context Window Management

The tagger and context agent receive only the last 10 turns. The writer receives the full last 20 turns. For longer conversations (10+ turns), the known_facts string in the writer brief provides a structured summary so the writer doesn't need to re-scan long history.

### 10. Score Drift Prevention

The tagger prompt includes: **"Hopelessness and desperation always INCREASE urgency. Emotional distress never lowers the urgency tag or any other tag."** This was an instruction in v6 but easily forgotten when the tagger is also generating the reply.

---

## Short Writer System Prompt (full text)

The writer's system prompt is ~120 words, not 600+:

```
You are Sonia Ribas — fertility coach, 15+ years experience, 700+ successful pregnancies.
You have seen hundreds of cases. You recognise patterns quickly. You speak directly as Sonia.
You are not a therapist. Not an AI. Not an assistant. Sonia.

Write the way a real person texts. Contractions. Natural rhythm. Light punctuation.
Use :) or :( when it fits — not every message. Incomplete sentences are fine.
Never use an em-dash (—). Never use markdown. Never write in paragraphs.
Never open mid-conversation with Hi, Hey, Hello, or I'm glad you reached out.
Never use: "I'm sorry to hear that", "What I'm hearing is", "That sounds difficult",
"I appreciate you sharing". No therapy language at all.
Ask at most ONE question per reply. If nothing to ask, ask nothing.
Never repeat a phrase from an earlier message in this conversation.

[cfg.prompt_hard_rules — injected verbatim]

YOUR TASK FOR THIS TURN:
[writer_brief — 15-20 lines, goal-specific, from the strategy engine]
```

---

## Files to Create / Modify

| File | Change | Notes |
|------|--------|-------|
| `app/services/orchestrator.py` | **New** | `TurnDirective` dataclass + `build_turn_directive()` — replaces most of `build_context_block()` in ai.py and routing logic in router.py |
| `app/services/ai.py` | **Refactor** | Split `generate_reply()` into: `_generate_writer_reply()`, `_classify_tags()`, `_quality_check()`, new `generate_reply()` orchestrating all three |
| `app/services/router.py` | **Update** | Add `emotion` field to `_run_classifier()` output and prompt; `build_route_context()` feeds into orchestrator |
| `app/services/webhook.py` | **Minor** | Add per-bubble send delays; call signature update |
| `app/services/simulate.py` | **Minor** | Call signature update; no delay logic |

`build_base_prompt()` and `build_context_block()` in ai.py are removed and replaced by the orchestrator's `writer_brief`.

---

## Cost Per Turn

| Stage | Input tokens | Output tokens | Cost (gpt-4.1-mini) |
|-------|-------------|---------------|---------------------|
| Context agent (Stage 2) | ~400 | ~60 | $0.00020 |
| Writer (Stage 4A) | ~600 | ~300 | $0.00060 |
| Tagger (Stage 4B) | ~500 | ~60 | $0.00025 |
| Quality gate (Stage 5) | ~500 | ~200 | $0.00028 |
| **Total** | | | **~$0.00133** |
| v6 (single call) | ~2,500 | ~130 | **~$0.00111** |

~20% cost increase. The quality improvement justifies this comfortably.

---

## Principles

The guiding question for every decision in this architecture: **"Would a human do this?"**

- Humans don't generate JSON tags while writing a warm message to someone who just had a miscarriage.
- Humans don't read a 600-word rulebook before deciding what to say.
- Humans decide tone first (is this a heavy moment?), then goal (what do I want to learn?), then write.

This architecture mirrors that. Each stage maps to how a skilled human would actually think through a response.