from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    REDIS_URL: str
    
    # API Keys
    OPENAI_API_KEY: str
    UNIPILE_API_KEY: str
    UNIPILE_DSN: str
    LINKEDIN_ACCOUNT_ID: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Generate key via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    COOKIE_ENCRYPTION_KEY: str
    ADMIN_PASSWORD: str

# Optional: Leave blank to disable Telegram alerts
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

# Dependency injection ke liye settings object
settings = Settings()