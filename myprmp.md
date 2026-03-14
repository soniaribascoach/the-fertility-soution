# Claude Code Instructions: FastAPI Admin Panel for Sonia Ribas DM System

## Context

You are building an admin panel for an AI-powered Instagram DM qualification system. The FastAPI backend handles incoming DMs, scores leads across 5 dimensions, and routes them to booking or human handoff. This admin panel allows the client (non-technical) to manage all "soft config" without touching code or redeploying.

The existing FastAPI app already has:
- PostgreSQL database (via SQLAlchemy or asyncpg)
- A `config` table (or you will create it) with `key` / `value` rows
- Webhook routes under `/webhook/...`

---

## Tech Stack Decision

Use **Jinja2 templates** (not a separate React frontend). Reasons:
- Already a FastAPI project — Jinja2 is the standard, first-party templating solution
- No build step, no separate JS bundler, no CORS config
- Admin panel is low-traffic internal tooling — SSR is perfectly appropriate
- Use **TailwindCSS via CDN** for styling (no build step needed)
- Use **HTMX** (via CDN) for any dynamic interactions (inline saves, list management) without writing JavaScript

Install dependencies:
```bash
pip install jinja2 python-multipart
```

---

## File Structure to Create

```
app/
├── admin/
│   ├── __init__.py
│   ├── router.py          # All admin routes
│   └── auth.py            # Simple password protection
├── templates/
│   ├── base.html          # Base layout
│   └── admin/
│       ├── index.html     # Dashboard / nav
│       ├── config.html    # Main config page
│       └── partials/
│           ├── blocklist_item.html   # HTMX partial for blocklist rows
│           └── toast.html            # Save confirmation toast
├── static/
│   └── admin.css          # Minimal custom styles if needed
└── models/
    └── config.py          # Config DB model + CRUD helpers
```

Mount the router in `main.py`:
```python
from app.admin.router import router as admin_router
app.include_router(admin_router, prefix="/admin")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
```

---

## Database: Config Table

Create this table if it doesn't exist:

```sql
CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Seed with defaults on first run:
```sql
INSERT INTO app_config (key, value) VALUES
  ('booking_link', 'https://calendly.com/your-link-here'),
  ('system_prompt', 'You are a warm, empathetic assistant for a fertility coaching brand...'),
  ('hard_nos', 'medication dosages, IVF clinic recommendations, pricing before qualification'),
  ('medical_blocklist', 'miscarriage,ectopic,chromosomal,IVF failure,chemical pregnancy'),
  ('score_threshold', '71')
ON CONFLICT (key) DO NOTHING;
```

Create a `ConfigModel` SQLAlchemy model and CRUD helpers:
- `get_config(key: str) -> str`
- `set_config(key: str, value: str) -> None`
- `get_all_config() -> dict`

---

## Authentication

Simple HTTP Basic Auth or a single hardcoded password via environment variable. Do NOT build a full user system — this is internal tooling.

```python
# auth.py
from fastapi import Request, HTTPException
from starlette.responses import RedirectResponse
import os

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

def require_auth(request: Request):
    if request.session.get("admin_authenticated") != True:
        raise HTTPException(status_code=401)
```

Add login/logout routes:
- `GET /admin/login` — renders login form
- `POST /admin/login` — checks password, sets session, redirects to `/admin`
- `GET /admin/logout` — clears session

Use `itsdangerous` sessions via Starlette's `SessionMiddleware`.

---

## Admin Routes to Build

### `GET /admin`
Redirect to `/admin/config` if authenticated, else to `/admin/login`.

### `GET /admin/config`
Renders `admin/config.html` with all config values loaded from DB.
Pass to template:
```python
{
  "booking_link": ...,
  "system_prompt": ...,
  "hard_nos": ...,
  "medical_blocklist": [...],  # split by comma into list
  "score_threshold": ...,
}
```

### `POST /admin/config/save`
Accepts form data. Updates DB for all standard fields (booking_link, system_prompt, hard_nos, score_threshold). Redirects back to `/admin/config` with a `?saved=true` query param to trigger a toast notification.

### `POST /admin/blocklist/add`
Accepts `term` from form. Appends to the `medical_blocklist` config value (comma-separated string in DB). Returns HTMX partial `blocklist_item.html` for the new row — no full page reload.

### `DELETE /admin/blocklist/remove`
Accepts `term` from form/query. Removes term from the list. Returns empty 200 or updated partial for HTMX to swap out the deleted row.

---

## UI: `base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Admin Panel – Sonia Ribas DM System</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.10"></script>
</head>
<body class="bg-gray-50 text-gray-800">
  <nav class="bg-white border-b px-6 py-4 flex justify-between items-center">
    <span class="font-semibold text-lg">DM System Admin</span>
    <a href="/admin/logout" class="text-sm text-gray-500 hover:text-red-500">Logout</a>
  </nav>
  <main class="max-w-3xl mx-auto py-10 px-4">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

---

## UI: `config.html` — Sections to Build

### Section 1: Booking Link
Simple text input, full URL. Label: "Booking Calendar Link". Help text: "This URL is sent to qualified leads. Update anytime."

### Section 2: Score Threshold
Number input (0–75). Label: "Qualification Score Threshold". Help text: "Leads scoring at or above this number receive the booking link. Default: 71."

### Section 3: System Prompt
Large `<textarea>` (min 12 rows, monospace font). Label: "AI System Prompt". Help text: "This controls the AI's tone, persona, and behavior. Changes take effect immediately."

### Section 4: Hard Nos
Regular `<textarea>` (4 rows). Label: "Hard Nos (comma-separated)". Help text: "Topics the AI will never engage with. E.g. medication dosages, pricing before qualification."

### Section 5: Medical Term Blocklist
Dynamic list — each term shown as a chip/row with a ❌ delete button. Add new terms via a small input + "Add" button. This section uses HTMX for inline add/remove without full page reloads.

```html
<!-- Example chip row (partial: blocklist_item.html) -->
<div id="term-{{ term }}" class="flex items-center gap-2 bg-red-50 border border-red-200 rounded px-3 py-1 text-sm">
  <span>{{ term }}</span>
  <button
    hx-delete="/admin/blocklist/remove?term={{ term }}"
    hx-target="#term-{{ term }}"
    hx-swap="outerHTML"
    class="text-red-400 hover:text-red-600 font-bold">✕</button>
</div>
```

### Save Button
One "Save Changes" button at the bottom that submits the full form (POST to `/admin/config/save`). Show a green toast on `?saved=true`.

---

## Important Implementation Notes

1. **Config is read at request time** — the webhook must call `get_config()` fresh per conversation (or use a short in-memory cache, e.g. 60-second TTL). Never hardcode config values in the webhook logic.

2. **Medical blocklist in webhook** — split the comma-separated string from DB into a list, then check `any(term.lower() in message.lower() for term in blocklist)` before passing to OpenAI.

3. **System prompt injection** — fetch `system_prompt` and `hard_nos` from DB, combine them before constructing the OpenAI messages array:
```python
full_system_prompt = f"{system_prompt}\n\nNever discuss: {hard_nos}"
```

4. **Booking link injection** — when the webhook decides to send the booking link (score ≥ threshold), fetch `booking_link` from config and interpolate into the AI response or a fixed template message.

5. **No client-side JS required** — all interactivity handled by HTMX attributes. Only exception: the toast notification on save, which can be a simple `{% if request.query_params.get('saved') %}` check in the template.

6. **Environment variables needed**:
   - `ADMIN_PASSWORD` — password to access the admin panel
   - `SECRET_KEY` — for session signing (use `secrets.token_hex(32)`)

---

## Security Notes

- Admin routes must all call `require_auth(request)` as a dependency
- Never expose the admin panel without the password gate — it controls AI behavior
- Do not log the system prompt or config values in application logs
- Rate-limit the login endpoint (3 attempts, then 15-minute lockout) — use a simple in-memory dict for MVP

---

## Acceptance Criteria

- [ ] Login page with password, session-based auth, logout
- [ ] Config page loads all 5 sections with current DB values
- [ ] Saving updates DB and shows confirmation toast
- [ ] Medical blocklist supports inline add/remove via HTMX (no full reload)
- [ ] Webhook reads all config from DB at runtime (no hardcoded values)
- [ ] Score threshold read from config and used in qualification logic
- [ ] System prompt + hard nos combined and passed to OpenAI
- [ ] Booking link injected into outbound message when threshold is crossed
- [ ] Admin panel is mobile-readable (Tailwind responsive classes)
- [ ] All sensitive config stored in env vars, not in code