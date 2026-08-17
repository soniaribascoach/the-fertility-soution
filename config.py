import os
import re
import subprocess
from datetime import datetime, timezone

from pydantic_settings import BaseSettings

# Product version shown in the admin UI. Bump on notable releases.
# v2.0 = three-stage brain: reader extracts facts, dossier gates them, brain writes.
APP_VERSION = "v2.0"

# Name of the brain generation, so the sidebar says which one is live, not only a number.
APP_BRAIN = "brain v2"

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _build_revision() -> str:
    """Short commit of the running code, so the admin UI can prove which build is deployed.

    The droplet deploys by pulling this repo and running start.sh, so .git is there.
    APP_REVISION wins when set, for a build that ships without a git directory.
    """
    from_env = os.getenv("APP_REVISION", "").strip()
    if from_env:
        return from_env[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


APP_REVISION = _build_revision()

# Process start, which on this deploy is the moment the new code went live.
APP_STARTED_AT = datetime.now(timezone.utc)



class Settings(BaseSettings):
    environment: str = "development"
    database_url: str
    openai_api_key: str
    admin_password: str = "changeme"
    secret_key: str = "changeme-set-a-real-secret-key"
    manychat_api_token: str = ""
    manychat_webhook_secret: str = ""
    worker_poll_interval: int = 3
    debounce_seconds: int = 15
    debounce_extra_seconds: int = 15
    max_typing_delay: float = 10.0

    @property
    def async_database_url(self) -> str:
        url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't support sslmode param; remove it
        url = re.sub(r"[?&]sslmode=[^&]*", "", url)
        url = re.sub(r"\?&", "?", url)
        return url

    class Config:
        env_file = ".env"


settings = Settings()
