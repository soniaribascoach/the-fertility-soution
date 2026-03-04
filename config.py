from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str
    openai_api_key: str

    class Config:
        env_file = ".env"


settings = Settings()
