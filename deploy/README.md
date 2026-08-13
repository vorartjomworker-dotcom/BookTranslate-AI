# Production deployment

Stage 9 includes a single-host hardened Compose baseline. It is intended as a reproducible production starting point, not as a replacement for a managed database, managed object store or Kubernetes when higher availability is required.

## 1. Prepare configuration

```bash
cp deploy/.env.production.example deploy/.env.production
```

Set at minimum:

- `APP_DOMAIN`
- a long random `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
- OIDC settings when SSO is enabled
- `VISION_MODEL` when figure OCR is enabled

`.env.production` is deployment-local and must not be committed.

## 2. Create mounted secrets

Follow `deploy/secrets/README.md`. Use mode `0600` for secret files. `database_url.txt` and `redis_url.txt` must contain the same PostgreSQL/Redis credentials configured for the bundled services.

For the bundled MinIO bootstrap, set `s3_access_key.txt` and `s3_secret_key.txt` to credentials accepted by that MinIO deployment. The minimal bundled configuration can use the MinIO root credentials; a hardened long-lived deployment should provision a dedicated application identity/policy or use external S3 and keep the same application-side secret file interface.

## 3. Install TLS material

Place `fullchain.pem` and `privkey.pem` in `deploy/tls/`. The private key is ignored by Git. The Nginx container terminates TLS, redirects HTTP to HTTPS, adds security headers and does not expose `/metrics` publicly.

## 4. Validate before starting

```bash
docker compose \
  --env-file deploy/.env.production \
  -f deploy/docker-compose.prod.yml \
  config -q
```

## 5. Start

```bash
docker compose \
  --env-file deploy/.env.production \
  -f deploy/docker-compose.prod.yml \
  up -d --build
```

The public surface is Nginx on ports 80/443. PostgreSQL, Redis, MinIO, backend and workers remain on the private Compose network. Prometheus is bound only to `127.0.0.1:9090`.

## 6. Verify

```bash
curl -fsS https://$APP_DOMAIN/liveness
curl -fsS https://$APP_DOMAIN/health
```

Use `/api/ops/status` and `/api/ops/slo` with an administrator application token. Prometheus scrapes `/metrics` internally using `deploy/secrets/metrics_token.txt` as Bearer credentials.

## Figure translation flow

```text
Original figure asset
  -> Vision/OCR
  -> figure_text segments + normalized bbox
  -> ordinary Translation / QA / Human Review
  -> FigureRenderJob
  -> Pillow renderer
  -> immutable translated PNG variant
  -> S3/MinIO or local storage
  -> translated DOCX/EPUB automatically uses latest completed variant
```

The original image is never overwritten. Rendering is fingerprinted and idempotent for the same source image, translations and bounding boxes.

## OpenTelemetry

The application and all workers can export OTLP traces to `otel-collector`. The bundled collector intentionally uses the `debug` exporter so no third-party telemetry credentials are required by the repository. Replace the exporter in `otel-collector.yml` with Tempo, Jaeger, Honeycomb, Datadog or another production trace backend.

## SLO baseline

Defaults:

- availability: 99.5%
- p95 API latency: <= 1 second

Prometheus rules alert on sustained availability/latency violations and worker lease contention. Tune them for production traffic and connect Prometheus to your Alertmanager/notification system.

## Backups

The existing local backup scripts remain valid for PostgreSQL/Redis/local uploads. With MinIO/S3 enabled, configure bucket versioning plus off-host replication or provider-native backups. Database backups and object-store backups must be tested together because document rows reference object keys.
