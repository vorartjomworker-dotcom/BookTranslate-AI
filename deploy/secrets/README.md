# Production secrets

Never commit the `.txt` files in this directory. The repository `.gitignore` here ignores them by default.

Create these files on the deployment host with restrictive permissions (`chmod 600 deploy/secrets/*.txt`):

- `database_url.txt` — full SQLAlchemy async URL, for example `postgresql+asyncpg://booktranslate:<password>@postgres:5432/booktranslate`
- `redis_url.txt` — full Redis URL containing the password from `redis_password.txt`
- `postgres_password.txt`
- `redis_password.txt`
- `bootstrap_admin_token.txt` — one-time bootstrap secret
- `auth_signing_secret.txt` — long random HMAC secret for download/SSO state signing
- `oidc_client_secret.txt` — may be an empty file when OIDC is disabled
- `s3_access_key.txt` — application MinIO/S3 access key
- `s3_secret_key.txt` — application MinIO/S3 secret key
- `openai_api_key.txt`
- `kimi_api_key.txt`
- `gemini_api_key.txt`
- `aitunnel_api_key.txt`
- `metrics_token.txt` — long random token used only by Prometheus

Provider key files may be empty when that provider is not enabled. In a managed deployment, prefer Docker/Kubernetes secrets or an external secret manager and mount the same values at the configured `*_FILE` paths.

For the bundled MinIO container, `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` are deployment bootstrap credentials from `.env.production`; keep that file outside source control and rotate them after provisioning. The application should use separate `s3_access_key.txt` / `s3_secret_key.txt` credentials with only the bucket permissions it needs.
