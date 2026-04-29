# Phase 1 Implementation Tracker

Webhook + Message Queue + Async AI Processing (tagging/scoring deferred to Phase 2)

## Tasks

- [x] `config.py` — add 4 new env vars (webhook secret, poll interval, debounce, max delay)
- [x] `app/models/pending_message.py` — pending_messages table model
- [x] `app/models/user_state.py` — user_state table model
- [x] `alembic/versions/k1e2f3a4b5c6_add_pending_messages.py` — migration
- [x] `alembic/versions/l2f3a4b5c6d7_add_user_state.py` — migration
- [x] `app/repositories/pending_message.py` — queue CRUD + lock/release logic
- [x] `app/repositories/user_state.py` — AI pause/resume logic
- [x] `app/services/manychat_client.py` — send_message only (no tagging yet)
- [x] `app/services/ai_pipeline.py` — extract AI logic from admin router
- [x] `app/services/output_parser.py` — strip markers, detect handover
- [x] `app/services/typing_delay.py` — humanized delay calculation
- [x] `app/api/webhook.py` — POST /webhook endpoint with HMAC verification
- [x] `app/worker.py` — debounce poller + handle_conversation async worker
- [x] `main.py` — wire worker + ManyChat client + webhook router into lifespan

## Deferred (Phase 2)

- [ ] ManyChat tagging (add_tag, remove_tag API calls)
- [ ] Lead scoring extraction (secondary gpt-4o-mini call)
- [ ] ManyChat custom field writes
- [ ] Spam protection (>15 msgs/10min)
- [ ] Admin UI: paused user list + resume button
- [ ] Deploy to production with HTTPS
- [ ] Configure ManyChat automation to call /webhook
- [ ] Smoke test with real IG account
