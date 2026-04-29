# Launch Plan: AI Chatbot → Instagram DMs via ManyChat

## Context

The AI chatbot (Sonia's voice) is functionally complete and tested in the admin sandbox. The goal is to wire it into real Instagram DMs: ManyChat triggers on every incoming DM, calls this app, and we send the reply back. This plan covers the full production-launch execution order, from ManyChat webhook integration through humanized delays, message batching, conversation context, ManyChat tagging, and operational hardening.

---

## Architecture: How It Must Work

```
IG User DMs Sonia
       ↓
ManyChat receives DM
       ↓
ManyChat calls POST /webhook on this app
       ↓
App immediately returns 200 OK (async processing begins in background)
       ↓
Debounce: wait 8s — if new message from same user arrives, reset timer
       ↓
Batch all pending messages → run AI pipeline
       ↓
Apply typing delay (proportional to response length)
       ↓
Call ManyChat API → send reply to user's IG DM
       ↓
Parse output markers → call ManyChat API → apply tags
```

**Key design constraints:**
- **Webhook must return 200 immediately** — ManyChat times out in ~5s
- **All AI processing happens async** in a background worker
- **Debounce window = 120s (2 minutes)** — waits for user to finish their full thought before generating one reply
- **Typing delay = (word count × 0.4s), randomized ±20%, capped at 45s** — not instant, not slow
- **All conversation history stored by `instagram_user_id`** — context persists across sessions
- **ManyChat automation handles:** flow gating, off-hours routing, webhook failure fallback — keeps app logic focused on AI

---

## Execution Steps

---

### STEP 1: Database — Add `pending_messages` Table

**Why:** We need a persistent queue to handle debounce and batching. PostgreSQL is already the stack; no Redis needed.

**What to build:**

**File: `app/models/pending_message.py`** (new)
```
Table: pending_messages
- id (PK)
- instagram_user_id (VARCHAR, indexed)
- content (TEXT) — the raw message text
- received_at (TIMESTAMP) — when ManyChat sent it
- processed_at (TIMESTAMP, nullable) — null = pending
```

**File: `app/repositories/pending_message.py`** (new)
- `insert_message(db, ig_user_id, content)` — add to queue
- `get_unprocessed_batch(db, ig_user_id)` — fetch all unprocessed for user
- `mark_batch_processed(db, ig_user_id)` — set processed_at = now
- `get_users_ready_to_process(db, debounce_seconds=8)` — returns ig_user_ids where max(received_at) < now - 8s AND processed_at IS NULL

**Migration:** Create Alembic migration for this table.

---

### STEP 2: Database — Add `user_state` Table

**Why:** Need to track whether AI is paused for a user (human takeover, medical, manual pause).

**File: `app/models/user_state.py`** (new)
```
Table: user_state
- instagram_user_id (PK)
- is_ai_paused (BOOLEAN, default false)
- paused_at (TIMESTAMP, nullable)
- pause_reason (VARCHAR) — "human_handover", "medical", "manual"
```

**File: `app/repositories/user_state.py`** (new)
- `get_state(db, ig_user_id)` — fetch or create state row
- `pause_ai(db, ig_user_id, reason)` — set is_ai_paused = true
- `resume_ai(db, ig_user_id)` — set is_ai_paused = false

**Migration:** Create Alembic migration for this table.

---

### STEP 3: ManyChat Webhook Endpoint

**Why:** This is the entry point. ManyChat will POST to this when an IG user sends a DM.

**File: `app/api/webhook.py`** (new)

**Endpoint: `POST /webhook`**

Request body (ManyChat sends this):
```json
{
  "id": "manychat_contact_id",
  "ig_id": "instagram_user_id",
  "ig_username": "username",
  "first_name": "Jane",
  "last_input_text": "I have PCOS and been trying for 2 years"
}
```

Logic:
1. Verify `X-ManyChat-Signature` HMAC-SHA256 header — reject with 401 if invalid
2. Parse `ig_id` and `last_input_text` from payload
3. If `last_input_text` is empty or None → return 200 immediately (button taps, etc.)
4. Deduplicate: check `pending_messages` for same user + same content within last 5s → skip if duplicate
5. Store message in `conversations` table (role=user) with `instagram_user_id = ig_id`
6. Insert into `pending_messages` table
7. **Return 200 OK immediately** — do NOT await AI processing

**Register in `main.py`:** `app.include_router(webhook_router)`

**Security:** Add `MANYCHAT_WEBHOOK_SECRET` to `.env` for signature verification.

---

### STEP 4: ManyChat API Client

**Why:** We need to call ManyChat to send replies and apply tags/custom fields.

**File: `app/services/manychat_client.py`** (new)

Uses `MANYCHAT_API_TOKEN` from env (already present). Uses `httpx.AsyncClient`.

**Methods needed:**
- `send_message(subscriber_id, text)` — POST to ManyChat Send Content API
- `add_tag(subscriber_id, tag_name)` — POST to ManyChat Tag API
- `remove_tag(subscriber_id, tag_name)` — POST to ManyChat Tag API
- `set_custom_field(subscriber_id, field_name, value)` — POST to ManyChat Custom Fields API

**ManyChat API base:** `https://api.manychat.com`
- Send message: `POST /fb/sending/sendContent`
- Add tag: `POST /fb/subscriber/addTag`
- Custom field: `POST /fb/subscriber/setCustomFieldByName`

**Auth header:** `Authorization: Bearer {MANYCHAT_API_TOKEN}`

**Error handling:** Retry up to 3 times with exponential backoff (1s, 2s, 4s) on 5xx errors. Never crash the worker — log failures and continue.

---

### STEP 5: Extract AI Pipeline as Reusable Service

**Why:** The AI pipeline logic currently lives inside the `/admin/chat` endpoint handler. The background worker needs the same logic. Extract it so both can share it.

**File: `app/services/ai_pipeline.py`** (new)

**Function: `generate_reply(db, ig_user_id, messages) -> str`**
- Accepts conversation history as message list
- Runs: medical blocklist check → pricing classifier → prompt builder → few shots → OpenAI call
- Returns raw AI output string (markers included, stripped later)
- Stores token usage and costs to DB

Both `/admin/chat` and the background worker call this function.

---

### STEP 6: Output Marker Parser

**Why:** The AI generates markers like `[HUMAN_HANDOVER]` but currently nothing acts on them.

**File: `app/services/output_parser.py`** (new)

```python
@dataclass
class ParsedOutput:
    clean_text: str
    is_handover: bool
    is_booking_sent: bool
    is_booking_asked: bool
    is_price_deflected: bool

def parse_ai_output(raw: str) -> ParsedOutput: ...
```

**Markers to parse (strip from text, return as flags):**
- `[HUMAN_HANDOVER]` → trigger handover flow
- `[BOOKING_SENT]` → apply ManyChat tag
- `[BOOKING_ASKED]` → apply ManyChat tag
- `[PRICE_DEFLECTED]` → apply ManyChat tag

---

### STEP 7: Typing Delay Service

**Why:** Instant replies are a clear AI tell. Simulated typing humanizes the experience.

**File: `app/services/typing_delay.py`** (new)

```python
def calculate_delay(reply_text: str) -> float:
    word_count = len(reply_text.split())
    base_delay = word_count * 0.4       # ~150 wpm
    jitter = random.uniform(0.8, 1.2)  # ±20% randomness
    return min(base_delay * jitter, 45.0)  # cap at 45 seconds
```

Called in the worker before sending reply:
```python
delay = calculate_delay(reply_text)
await asyncio.sleep(delay)
await manychat_client.send_message(ig_user_id, reply_text)
```

---

### STEP 8: Background Worker — Debounce + Batch Processor

**Why:** The AI pipeline runs here, after the debounce window closes. This is the core of the async architecture.

**File: `app/worker.py`** (new)

**Mechanism:** A polling loop started in the app's `lifespan` context in `main.py`:

```python
async def process_loop():
    while True:
        await asyncio.sleep(WORKER_POLL_INTERVAL)  # every 3 seconds
        ready_users = await get_users_ready_to_process(db, debounce_seconds=120)
        for ig_user_id in ready_users:
            if ig_user_id not in processing_users:
                asyncio.create_task(handle_conversation(ig_user_id))
```

**`handle_conversation(ig_user_id)` logic:**
1. Add to `processing_users` set (concurrency guard — prevents double-processing)
2. Check `user_state` — if `is_ai_paused`, skip and return
3. Fetch all pending messages for user (ordered by `received_at`)
4. Mark them as processed immediately (prevent re-pickup)
5. Concatenate messages with newline separator if multiple (e.g., user sent 4 messages → one combined input to AI)
6. Check if this is first-ever contact for user (no prior conversation history)
7. Retrieve conversation history from `conversations` table (last 20 messages)
8. Call `generate_reply()` from `ai_pipeline.py`
9. Parse output markers via `output_parser.py`
10. Store AI reply in `conversations` table (role=assistant)
11. Calculate and apply typing delay
12. Send reply via `manychat_client.send_message()`
13. Apply ManyChat tags based on parsed markers
14. Run lead scoring extraction (Step 10)
15. Remove from `processing_users` set in `finally` block

**Why 2-minute debounce stays in the app, not ManyChat:**
ManyChat's "restart on new message" flow resets the wait timer but only passes `last_input_text` — earlier messages in the window are lost. Our `pending_messages` table captures every message as it arrives, so when the 2-minute window closes, we batch all of them into one AI input. This is the key difference: ManyChat debounce = last message only; app debounce = all messages combined.

**Worker crash recovery:** Because pending messages are in PostgreSQL, a worker restart will re-pick unprocessed messages in the next poll cycle. Only mark `processed_at` after successful send.

---

### STEP 9: Human Takeover — Pause AI for User

**Logic in worker:** Before running AI pipeline for a user, check `user_state.is_ai_paused`. If true, skip — log that message was received but AI skipped.

**When to pause:**
- `[HUMAN_HANDOVER]` marker detected in AI output → `pause_ai(ig_user_id, "human_handover")`
- Medical keyword matched → `pause_ai(ig_user_id, "medical")`
- Non-English message detected → `pause_ai(ig_user_id, "non_english")`

**Admin UI — add to dashboard:**
- List of currently paused users with pause reason and timestamp
- "Resume AI" button per user → calls `resume_ai()` + removes `AI Handover` tag in ManyChat

---

### STEP 10: Lead Scoring & Diagnosis Extraction

**Why:** `lead_score` and `contact_tags` fields exist in DB but are never populated.

**Approach:** After each AI response, run a second lightweight LLM call with a structured extraction prompt:

```
Given this conversation, extract as JSON:
{
  "lead_score": 1-10,
  "diagnosis": "pcos|low_amh|unexplained|miscarriage|ivf_failed|other|unknown",
  "ttc_duration": "<1yr|1-2yr|2-3yr|3+yr|unknown",
  "prior_treatments": ["ivf", "iui", "letrozole", ...],
  "urgency": "high|medium|low",
  "partner_involved": true|false|null
}
```

- Use `gpt-4o-mini`, temp=0 (deterministic extraction)
- Cost: ~$0.001 per message — acceptable
- Store JSON in `conversations.contact_tags` for that assistant message
- Map `urgency: high` + `lead_score >= 7` → add "Hot Lead" tag in ManyChat
- Map `diagnosis` → set ManyChat custom field `Detected Diagnosis`

---

### STEP 11: ManyChat Tags — To Be Finalized

> **Note:** Specific tags will be decided separately. Keep the list small and purposeful — each tag should drive a distinct automation branch or segment. The ones below are the minimum viable set; trim further as needed.

**Suggested minimum tags (pending review):**
- `AI Handover` — human needs to take over, AI stops replying
- `Medical Query` — medical keyword triggered, needs human review
- `Booking Link Sent` — for follow-up automation sequences

**Suggested custom fields:**
- `AI Paused` — boolean, checked by ManyChat before calling webhook (gates the AI flow)
- `Lead Score` — numeric 1–10, used for segmentation
- `Detected Diagnosis` — string, used for personalized follow-up sequences

---

### STEP 12: Conversation Context & Token Budget

**Current:** `get_history()` fetches last 20 messages — sufficient for most conversations.

**Guard:** If `prompt_tokens` for any recent message exceeds 80,000 → drop to last 10 messages for that call. Log a warning.

**Conversation Reset:** If `max(created_at)` for a user's conversation is > 30 days ago, treat as new conversation. Start fresh context. History stays in DB for analytics but is not injected into OpenAI call.

Add `conversation_reset_days` to `app_config` table (default: 30, editable via admin UI).

---

### STEP 13: Edge Case Handling

**First message detection:** If no prior conversation exists for a user, inject a first-contact instruction into the system prompt — warmer opening, no assumed prior context.

**Bot/button tap detection:** If `last_input_text` matches a known ManyChat button payload (predefined phrases like "Get Started", "Learn More") → skip AI processing, return 200 silently.

**Spam protection:** If a user sends > 15 messages within 10 minutes → pause AI, add tag `High Frequency Sender`, alert team.

**Long silence re-engagement:** Handled by conversation reset logic in Step 12.

**Duplicate webhook protection:** ManyChat may retry failed webhooks. Deduplicate by checking `pending_messages` for same `ig_user_id` + same `content` within 5 seconds.

---

### STEP 14: Error Handling & Fallbacks

**OpenAI failure:** If API call fails after 3 retries, send a fallback message via ManyChat: `"Thanks for reaching out — Sonia will get back to you shortly."` Apply tag `AI Error - Needs Human`.

**ManyChat send failure:** Log to `events` table with full payload. Retry 3x with backoff. If all fail, log as critical and (future) alert via email/Slack.

**Worker crash recovery:** Pending messages stay in PostgreSQL. Restart picks them up in next poll cycle. `processed_at` only set after successful send.

---

### STEP 15: New Environment Variables

Add to `.env` and `.env.example`:

```
MANYCHAT_WEBHOOK_SECRET=<from manychat>   # HMAC signature verification
WORKER_POLL_INTERVAL=3                    # seconds between worker polls
DEBOUNCE_SECONDS=120                      # 2-minute message batching window
MAX_TYPING_DELAY=45                       # seconds cap on delay
CONTEXT_RESET_DAYS=30                     # days before treating as new conversation
```

---

### STEP 16: Deployment

- App must be publicly accessible over HTTPS (required by ManyChat)
- Use a reverse proxy (Nginx or Caddy) in front of Uvicorn
- Run with `--workers 1` — async tasks share in-memory `processing_users` set
- Platforms: Railway, Render, Fly.io, or a VPS with Docker
- Ensure `DATABASE_URL` points to production PostgreSQL

**ManyChat automation setup:**
1. In ManyChat, create/edit the IG DM automation
2. Add "External Request" action: `POST https://yourdomain.com/webhook`
3. Map fields in request body: `ig_id`, `first_name`, `last_input_text`
4. Set ManyChat timeout to 10s (their max)
5. Create all tags and custom fields from Step 11 before launch

---

## ManyChat Automation Builder — What to Configure There (Not in Code)

Several things are better handled as no-code steps inside the ManyChat flow builder rather than in the app. This keeps the app focused on AI logic and lets the team adjust behavior without touching code.

### Flow Structure (in ManyChat)

```
User sends IG DM
       ↓
[Step 1] Check custom field: AI Paused = true?
       → Yes → Route to "Human is handling this" branch (silent or holding message)
       → No  → Continue
       ↓
[Step 2] Check time of day (business hours?)
       → Off-hours → Send holding message: "Sonia will be with you shortly ☀️"
                     Tag: [off-hours queue] or hand to human
       → In-hours → Continue
       ↓
[Step 3] POST to /webhook (External Request)
       → Success (200) → Done — app handles everything from here
       → Failure / timeout → Send fallback: "Thanks for reaching out — we'll get back to you shortly"
                             Add tag: AI Error - Needs Human
```

### Why This Split Works Well

| Concern | Handled by |
|---------|-----------|
| Is AI paused for this user? | ManyChat (checks `AI Paused` field before calling webhook) |
| Off-hours routing | ManyChat (time conditions, no code) |
| Webhook failure fallback | ManyChat (built-in failure branch, no retry logic needed in app) |
| Message debounce + batching | App (ManyChat can't aggregate multiple messages, only last_input_text) |
| AI reply generation + delay | App |
| Conversation history + context | App |
| Lead scoring, tagging, handover | App (calls ManyChat API after processing) |

### ManyChat Flow Settings
- **"Restart automation on new message":** Enable this on the DM trigger — ensures each new message re-enters the flow fresh rather than stacking parallel flows
- **Timeout on External Request:** Set to 10s (ManyChat max) — our app returns 200 immediately so this will always succeed unless the server is down (caught by failure branch)

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `app/models/pending_message.py` | CREATE |
| `app/models/user_state.py` | CREATE |
| `app/repositories/pending_message.py` | CREATE |
| `app/repositories/user_state.py` | CREATE |
| `app/api/webhook.py` | CREATE |
| `app/services/manychat_client.py` | CREATE |
| `app/services/typing_delay.py` | CREATE |
| `app/services/output_parser.py` | CREATE |
| `app/services/ai_pipeline.py` | CREATE (extract from admin router) |
| `app/worker.py` | CREATE |
| `app/api/admin/router.py` | MODIFY — add paused user management UI |
| `main.py` | MODIFY — register webhook router, start worker loop in lifespan |
| `alembic/versions/` | ADD — migrations for pending_message, user_state |
| `.env` / `.env.example` | MODIFY — add new env vars |

---

## Build Order (Sequential Dependencies)

```
1.  pending_messages model + migration
2.  user_state model + migration
3.  ManyChat API client
4.  Extract ai_pipeline.py from admin router
5.  Output marker parser
6.  Typing delay service
7.  Webhook endpoint (/webhook)
8.  Background worker (process_loop + handle_conversation)
9.  Wire worker into main.py lifespan
10. Human handover pause/resume logic
11. Admin UI: paused user list + resume button
12. Lead scoring extraction (secondary LLM call)
13. ManyChat tagging + custom field writes
14. Edge case handlers (spam, duplicate, first contact, bot tap)
15. Observability: admin dashboard metrics
16. Deploy to production with HTTPS
17. Configure ManyChat automation to hit /webhook
18. Smoke test with real IG account
```

---

## Verification & Testing

| Test | What to check |
|------|--------------|
| Webhook smoke test | POST fake payload → 200 immediate, message in `pending_messages`, AI reply in `conversations` after ~15s |
| Message batching | 3 rapid messages → only 1 AI reply from concatenated batch |
| Typing delay | Reply arrives 10–45s after send, timestamp in DB confirms |
| Human handover | Trigger phrase → marker stripped from user message, `AI Handover` tag in ManyChat, subsequent messages get no AI reply |
| Medical keyword | Blocklist phrase → deflection response sent, `Medical Query` tag applied |
| Context persistence | Follow-up message → AI reply references prior message content |
| Worker crash recovery | Kill app mid-processing → restart → pending message processed next cycle |
| Webhook signature | Invalid/no signature → 401 returned |
| Conversation reset | User with last message 31+ days ago → AI treats as new conversation |
| Spam protection | 16 messages in 10 min → AI paused, `High Frequency Sender` tag applied |

---

## Real-World Considerations (Advisory)

1. **Off-hours replies:** Handled in ManyChat automation (time condition branch) — no app code needed. ManyChat routes to a holding message or human queue outside business hours.

2. **GDPR / data deletion:** When a user requests deletion, purge their rows from `conversations`, `pending_messages`, `user_state`. Add a simple admin endpoint for this.

3. **ManyChat contact ID vs IG ID:** ManyChat assigns its own subscriber ID. The `ig_id` is the stable Instagram user ID. Store both; use `ig_id` as the database key (what we already do).

4. **Config audit log:** When admin changes prompt config, log who changed what and when. Prevents "who broke the prompts" situations.

5. **A/B testing:** Once live, consider running two prompt variants (via a feature flag in `app_config`) to measure conversion rate differences. Not for launch, but design for it.

6. **ManyChat typing indicator:** ManyChat may support a "typing" indicator action. If available, trigger it from the app at delay start (before `asyncio.sleep`) and send message when delay ends — maximally realistic.
