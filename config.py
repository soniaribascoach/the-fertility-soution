import re
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str
    openai_api_key: str
    admin_password: str = "changeme"
    secret_key: str = "changeme-set-a-real-secret-key"
    manychat_api_token: str = ""
    phoenix_collector_endpoint: str = ""
    phoenix_api_key: str = ""

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
