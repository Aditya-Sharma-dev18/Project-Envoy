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

# Dependency injection ke liye settings object
settings = Settings()