import re
from pydantic_settings import BaseSettings

# Product version shown in the admin UI. Bump on notable releases.
# v1.1 = qualification-funnel brain (see specs/brain_architecture.md).
APP_VERSION = "v1.1"

# Which brain answers when `brain_version` is absent from app_config. The key is
# seeded by migration, so this only applies to a database predating it.
# "funnel" and "legacy" stay selectable; rollback is that one config field.
DEFAULT_BRAIN = "routed"


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
