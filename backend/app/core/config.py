from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BookTranslate AI API"
    app_environment: str = "development"
    database_url: str = "postgresql+asyncpg://booktranslate:booktranslate@postgres:5432/booktranslate"
    redis_url: str = "redis://redis:6379/0"
    upload_dir: str = "/data/uploads"
    max_upload_size_mb: int = 100

    storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "booktranslate"
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_access_key_file: str | None = None
    s3_secret_key_file: str | None = None
    s3_use_ssl: bool = False
    s3_addressing_style: str = "path"
    storage_presign_ttl_seconds: int = 120

    auth_required: bool = False
    bootstrap_admin_token: str | None = None
    bootstrap_admin_token_file: str | None = None
    auth_signing_secret: str | None = None
    auth_signing_secret_file: str | None = None
    download_ticket_ttl_seconds: int = 120
    cors_origins: str = "http://localhost:3000"

    oidc_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_client_secret_file: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/api/auth/oidc/callback"
    oidc_frontend_redirect_uri: str = "http://localhost:3000/auth/callback"
    oidc_scopes: str = "openid email profile"
    oidc_role_claim: str = "booktranslate_role"
    oidc_default_role: str = "viewer"

    ai_request_timeout_seconds: int = 120
    openai_api_key: str | None = None
    openai_api_key_file: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    kimi_api_key: str | None = None
    kimi_api_key_file: str | None = None
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    gemini_api_key: str | None = None
    gemini_api_key_file: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    aitunnel_api_key: str | None = None
    aitunnel_api_key_file: str | None = None
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

    figure_render_queue_name: str = "figure-render"
    figure_render_worker_poll_seconds: int = 5
    figure_render_job_recovery_age_seconds: int = 900
    figure_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    figure_render_min_font_size: int = 8
    figure_render_max_font_size: int = 48
    figure_render_padding_px: int = 2

    translation_queue_name: str = "translation"
    translation_worker_poll_seconds: int = 5
    translation_job_recovery_age_seconds: int = 900

    worker_lease_seconds: int = 180
    worker_lease_renew_seconds: int = 45

    metrics_token: str | None = None
    metrics_token_file: str | None = None
    audit_enabled: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "booktranslate-api"
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4318"
    otel_exporter_otlp_headers: str | None = None
    slo_availability_target: float = 0.995
    slo_p95_latency_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        secret_files = {
            "s3_access_key": self.s3_access_key_file,
            "s3_secret_key": self.s3_secret_key_file,
            "bootstrap_admin_token": self.bootstrap_admin_token_file,
            "auth_signing_secret": self.auth_signing_secret_file,
            "oidc_client_secret": self.oidc_client_secret_file,
            "openai_api_key": self.openai_api_key_file,
            "kimi_api_key": self.kimi_api_key_file,
            "gemini_api_key": self.gemini_api_key_file,
            "aitunnel_api_key": self.aitunnel_api_key_file,
            "metrics_token": self.metrics_token_file,
        }
        for field_name, file_name in secret_files.items():
            if getattr(self, field_name) or not file_name:
                continue
            value = Path(file_name).read_text(encoding="utf-8").strip()
            if value:
                setattr(self, field_name, value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


settings = Settings()
