# Production deployment

BookTranslate AI has two supported production baselines:

1. **single-host Docker Compose** in this directory;
2. **Kubernetes/Helm** in `deploy/helm/booktranslate/` for independently scalable stateless services and workers.

The Compose target is a hardened reproducible starting point. Higher availability should use managed/clustered PostgreSQL, Redis and S3-compatible storage and the Helm chart.

## 1. Prepare configuration

```bash
cp deploy/.env.production.example deploy/.env.production
```

Set at minimum:

- `APP_DOMAIN`;
- strong MinIO bootstrap credentials when using the bundled MinIO;
- OIDC settings when SSO is enabled;
- `SCIM_ENABLED=true` when directory provisioning is enabled;
- `VISION_MODEL` when figure OCR is enabled;
- session TTL/provider feedback/render-mode values when deviating from defaults.

`.env.production` is deployment-local and must not be committed.

## 2. Create mounted secrets

Follow `deploy/secrets/README.md` and use mode `0600`. Important independent values include:

- database URL/password;
- Redis URL/password;
- bootstrap and HMAC signing secrets;
- OIDC client secret;
- SCIM bearer token;
- S3/MinIO application credentials;
- provider API keys;
- metrics bearer token.

Do not reuse the same secret value between application signing, metrics, SCIM and provider authentication.

## 3. Install TLS material

Place `fullchain.pem` and `privkey.pem` in `deploy/tls/`. Both are excluded from source control. Nginx:

- redirects HTTP to HTTPS;
- terminates TLS 1.2/1.3;
- adds security headers;
- proxies `/api/` and `/scim/` to FastAPI;
- proxies the remaining browser routes to Next.js;
- denies public `/metrics`.

## 4. Validate before starting

```bash
docker compose \
  --env-file deploy/.env.production \
  -f deploy/docker-compose.prod.yml \
  config -q
```

CI performs this same config validation and also executes `nginx -t` with an ephemeral test certificate.

## 5. Start

```bash
docker compose \
  --env-file deploy/.env.production \
  -f deploy/docker-compose.prod.yml \
  up -d --build
```

Only Nginx 80/443 is public. PostgreSQL, Redis, MinIO, FastAPI and workers stay on the private network. Prometheus is bound to `127.0.0.1:9090`.

## 6. Verify

```bash
curl -fsS https://$APP_DOMAIN/liveness
curl -fsS https://$APP_DOMAIN/health
```

Use `/api/ops/status` and `/api/ops/slo` with an administrator token. Prometheus scrapes `/metrics` internally with `metrics_token.txt` as Bearer credentials.

## OIDC sessions and SCIM

OIDC browser sign-in uses independent expiring access/refresh sessions rather than rotating one user-wide API token. Refresh tokens are single-use and rotated transactionally. Session endpoints support listing and revocation.

When SCIM is enabled, expose your IdP provisioner to:

```text
https://<APP_DOMAIN>/scim/v2
```

Use a dedicated `scim_bearer_token.txt`. SCIM creates/deactivates application users and maps deterministic groups to BookTranslate roles. Deprovisioning revokes active browser sessions.

## Figure translation flow

```text
Original figure asset (immutable)
  → Vision/OCR
  → figure_text + normalized bbox
  → Translation / QA / Human Review
  → FigureRenderJob
  → overlay | OpenCV inpaint | vector
  → immutable translated PNG
  → optional editable SVG sidecar
  → S3/MinIO/local storage
  → translated DOCX/EPUB
```

`inpaint` is the production default. It masks OCR regions and uses OpenCV Telea reconstruction before translated text is fitted. `vector` also stores an SVG sidecar with editable translated text.

## Adaptive model scheduling

The application combines static model policy with provider feedback. Successful and throttled responses can update short-lived Redis state containing remaining request/token capacity, reset windows and `Retry-After`. The adaptive route can avoid a temporarily exhausted provider/model while other configured candidates continue.

## OpenTelemetry and SLO

The API/workers can export OTLP traces to `otel-collector`. The bundled collector deliberately uses a debug exporter; connect it to your durable tracing backend in a real deployment.

Default SLO:

- availability: 99.5%;
- p95 API latency: <= 1 second.

Prometheus alerts cover SLO breaches and worker lease contention.

## Backup and restore verification

Normal scripts:

```bash
./scripts/backup.sh
./scripts/restore.sh ./backups/<timestamp>
```

Stage 10 adds a destructive local restore drill:

```bash
./scripts/restore_drill.sh
```

It verifies PostgreSQL, Redis and persistent file state by creating markers, backing them up, deleting them, restoring and checking that all three markers return. The GitHub Actions `Restore Drill` workflow runs this in an isolated Compose stack weekly and on demand.

When production storage is external S3/MinIO, configure bucket versioning/replication or provider-native backups separately and perform an environment-specific restore drill that validates database/object-key consistency.

## Kubernetes

For horizontal scaling and managed state, use `deploy/helm/booktranslate/README.md`. The Helm target includes migration hooks, HPA, optional KEDA Redis queue scaling, PDB, NetworkPolicy, TLS Ingress and an optional authenticated ServiceMonitor.
