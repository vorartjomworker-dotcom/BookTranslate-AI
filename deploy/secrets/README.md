# Production secrets

Never commit the `.txt` files in this directory. The repository `.gitignore` here ignores them by default.

Create these files on the deployment host with restrictive permissions (`chmod 600 deploy/secrets/*.txt`):

- `database_url.txt` — full SQLAlchemy async URL, for example `postgresql+asyncpg://booktranslate:<password>@postgres:5432/booktranslate`
- `redis_url.txt` — full Redis URL containing the password from `redis_password.txt`
- `postgres_password.txt`
- `redis_password.txt` — also maps to the `redis-password` key in the Kubernetes Secret when KEDA Redis autoscaling is enabled
- `bootstrap_admin_token.txt` — one-time bootstrap secret
- `auth_signing_secret.txt` — long random HMAC secret for download/SSO state signing
- `oidc_client_secret.txt` — may be an empty file when OIDC is disabled
- `scim_bearer_token.txt` — independent long random token for `/scim/v2`; may be empty only when SCIM is disabled
- `s3_access_key.txt` — application MinIO/S3 access key
- `s3_secret_key.txt` — application MinIO/S3 secret key
- `openai_api_key.txt`
- `kimi_api_key.txt`
- `gemini_api_key.txt`
- `aitunnel_api_key.txt`
- `metrics_token.txt` — long random token used only by Prometheus

Provider key files may be empty when that provider is not enabled. SCIM, metrics, bootstrap, application signing and provider credentials must be independent values rather than reusing one shared secret.

For Kubernetes, the Helm chart references an externally managed Secret named by `secrets.existingSecret` and never creates production credentials from Helm values. Prefer External Secrets Operator, Secrets Store CSI, Vault or the cloud provider's secret manager. KEDA additionally expects a separate Redis password key because its Redis List scaler consumes `host:port` and password independently from the application's full `REDIS_URL`.

For the bundled MinIO container, `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` are deployment bootstrap credentials from `.env.production`; keep that file outside source control. The simplest single-host bootstrap is to put the same access/secret values into `s3_access_key.txt` and `s3_secret_key.txt`. For a hardened long-lived deployment, provision a separate MinIO/S3 application identity scoped to the BookTranslate bucket, put those dedicated credentials in the two S3 secret files, and rotate the root credentials after provisioning.
