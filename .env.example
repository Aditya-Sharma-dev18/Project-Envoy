from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database & Queue
    DATABASE_URL: str
    REDIS_URL: str

    # LLM Parser
    OPENAI_API_KEY: str

    # Security & Admin UI
    COOKIE_ENCRYPTION_KEY: str
    ADMIN_PASSWORD: str

    # Playwright Behavior (Set False locally for visual smoke test)
    PLAYWRIGHT_HEADLESS: bool = True

    # Optional Alerting (Leave blank to disable)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()