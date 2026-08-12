from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BookTranslate AI API"
    database_url: str = "postgresql+asyncpg://booktranslate:booktranslate@postgres:5432/booktranslate"
    redis_url: str = "redis://redis:6379/0"
    upload_dir: str = "/data/uploads"
    max_upload_size_mb: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
