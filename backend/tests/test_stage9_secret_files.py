from pathlib import Path

from app.core.config import Settings


def test_secret_files_override_environment_values(tmp_path: Path) -> None:
    database = tmp_path / "database_url"
    redis = tmp_path / "redis_url"
    signing = tmp_path / "auth_signing_secret"
    metrics = tmp_path / "metrics_token"
    database.write_text("postgresql+asyncpg://file-user:file-pass@db:5432/books\n", encoding="utf-8")
    redis.write_text("redis://:secret@redis:6379/0\n", encoding="utf-8")
    signing.write_text("signing-from-file\n", encoding="utf-8")
    metrics.write_text("metrics-from-file\n", encoding="utf-8")

    config = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://env:env@localhost/db",
        database_url_file=str(database),
        redis_url="redis://localhost:6379/0",
        redis_url_file=str(redis),
        auth_signing_secret="from-env",
        auth_signing_secret_file=str(signing),
        metrics_token_file=str(metrics),
    )

    assert config.database_url == "postgresql+asyncpg://file-user:file-pass@db:5432/books"
    assert config.redis_url == "redis://:secret@redis:6379/0"
    assert config.auth_signing_secret == "signing-from-file"
    assert config.metrics_token == "metrics-from-file"
