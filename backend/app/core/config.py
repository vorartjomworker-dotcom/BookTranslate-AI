from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BookTranslate AI API"
    database_url: str = "postgresql+asyncpg://booktranslate:booktranslate@postgres:5432/booktranslate"
    redis_url: str = "redis://redis:6379/0"
    upload_dir: str = "/data/uploads"
    max_upload_size_mb: int = 100

    auth_required: bool = False
    bootstrap_admin_token: str | None = None
    auth_signing_secret: str | None = None
    download_ticket_ttl_seconds: int = 120
    cors_origins: str = "http://localhost:3000"

    oidc_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/api/auth/oidc/callback"
    oidc_frontend_redirect_uri: str = "http://localhost:3000/auth/callback"
    oidc_scopes: str = "openid email profile"
    oidc_role_claim: str = "booktranslate_role"
    oidc_default_role: str = "viewer"

    ai_request_timeout_seconds: int = 120
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    kimi_api_key: str | None = None
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    aitunnel_api_key: str | None = None
    aitunnel_base_url: str = "https://api.aitunnel.ru/v1"

    vision_provider: str = "openai"
    vision_model: str | None = None
    vision_queue_name: str = "vision"
    vision_worker_poll_seconds: int = 5
    vision_job_recovery_age_seconds: int = 900
    vision_prompt: str = (
        "Extract every meaningful text region from this technical figure. Return strict JSON with keys "
        "text, has_text, and regions. regions must be an array of objects with text, kind, and bbox; bbox "
        "is [x1,y1,x2,y2] normalized to 0..1 when it can be estimated. Do not invent text that is not visible."
    )

    translation_queue_name: str = "translation"
    translation_worker_poll_seconds: int = 5
    translation_job_recovery_age_seconds: int = 900

    metrics_token: str | None = None
    audit_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


settings = Settings()
