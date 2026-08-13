from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BookTranslate AI API"
    database_url: str = "postgresql+asyncpg://booktranslate:booktranslate@postgres:5432/booktranslate"
    redis_url: str = "redis://redis:6379/0"
    upload_dir: str = "/data/uploads"
    max_upload_size_mb: int = 100

    ai_request_timeout_seconds: int = 120
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    kimi_api_key: str | None = None
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    aitunnel_api_key: str | None = None
    aitunnel_base_url: str = "https://api.aitunnel.ru/v1"

    translation_queue_name: str = "translation"
    translation_worker_poll_seconds: int = 5
    translation_job_recovery_age_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
