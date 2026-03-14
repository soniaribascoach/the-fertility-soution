import time
from fastapi import Request
from config import settings

# in-memory rate limiter: {ip: {"attempts": int, "locked_until": float}}
_rate_limit_store: dict[str, dict] = {}

MAX_ATTEMPTS = 3
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def is_authenticated(request: Request) -> bool:
    return request.session.get("admin_authenticated") is True


def check_rate_limit(request: Request) -> bool:
    """Returns True if the request is allowed (not rate-limited)."""
    ip = request.client.host
    entry = _rate_limit_store.get(ip)
    if entry and entry.get("locked_until", 0) > time.time():
        return False
    return True


def record_failed_attempt(request: Request) -> int:
    """Records a failed login attempt and returns remaining attempts."""
    ip = request.client.host
    entry = _rate_limit_store.setdefault(ip, {"attempts": 0, "locked_until": 0})
    entry["attempts"] += 1
    if entry["attempts"] >= MAX_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS
    return max(0, MAX_ATTEMPTS - entry["attempts"])


def reset_attempts(request: Request) -> None:
    ip = request.client.host
    _rate_limit_store.pop(ip, None)
