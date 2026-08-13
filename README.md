# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, provider-neutral AI orchestration, durable workers, multi-model QA, human review, figure OCR/redraw, SSO/RBAC, object storage and browser translator/reviewer workspaces.

## Current status

- **Stage 1 — Infrastructure ✅** Next.js + TypeScript, FastAPI, PostgreSQL, Redis, Docker Compose, health checks and CI.
- **Stage 2 — Document Engine ✅** `Book → Chapter → Section → Block → Segment`, assets, figures, tables, captions, DOCX/EPUB parsing and reconstruction.
- **Stage 3 — Translation Engine ✅** Translation history, ModelRun audit, prompts, glossary, Translation Memory, Context Builder and OpenAI/Kimi/Gemini/AITUNNEL gateway.
- **Stage 4 — Jobs, Workers & Multi-model QA ✅** durable Redis jobs, retries/recovery, progress, multi-model QA and translated DOCX.
- **Stage 5 — Human Review, Book QA & Adaptive Routing ✅** approval/edit/reject, terminology audit, provider policies, budgets and application-side rate controls.
- **Stage 6 — EPUB Fidelity & Translator Workbench ✅** translated EPUB, hyperlink/formula fidelity metadata, source↔target browser editor and QA dashboard.
- **Stage 7 — Notes, RBAC & Reviewer Workflow ✅** first-class footnote/endnote translation, roles, assignments, comments, version diff and reviewer inbox.
- **Stage 8 — Vision/OCR, SSO, Security & Operations ✅** figure OCR, OIDC, full API perimeter, signed downloads, Prometheus, audit and backup/restore foundation.
- **Stage 9 — Figure Redraw, Object Storage & Production Telemetry ✅** translated figure variants, S3/MinIO, distributed worker leases, OpenTelemetry, SLO definitions and hardened TLS deployment baseline.

## Stage 9 architecture

```text
Original figure asset (immutable)
        ↓
VisionJob / Vision worker
        ↓
OCR regions + normalized bbox
        ↓
Segment(type=figure_text)
        ↓
Translation → Multi-model QA → Human Review
        ↓
FigureRenderJob / render worker
        ↓
Pillow bbox renderer + DejaVu Sans
        ↓
immutable translated PNG variant
        ↓
LocalStorage or S3/MinIO
        ↓
translated DOCX / EPUB automatically selects
latest completed render for the target language
```

Figure rendering is fingerprinted and idempotent. The fingerprint includes the source asset SHA-256, language, figure-text segment identities, source hashes, translations and bounding boxes. Re-running the same render does not create a duplicate variant.

The renderer estimates each OCR region background from its corners, chooses a contrast foreground, wraps/fits translated text into the region and records regions that may overflow. It never overwrites the original asset.

## Storage

The application uses a single `StorageBackend` contract:

```text
LocalStorage
S3Storage ──► AWS S3 / MinIO / S3-compatible object stores
```

Local storage remains the default and is backward compatible with existing books. New S3/MinIO deployments store source documents, parsed assets and rendered figures by object key. S3 downloads can use native short-lived presigned URLs.

Example local configuration:

```env
STORAGE_BACKEND=local
UPLOAD_DIR=/data/uploads
```

Example MinIO configuration:

```env
STORAGE_BACKEND=minio
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=booktranslate
S3_REGION=us-east-1
S3_ACCESS_KEY_FILE=/run/secrets/s3_access_key
S3_SECRET_KEY_FILE=/run/secrets/s3_secret_key
S3_USE_SSL=false
S3_ADDRESSING_STYLE=path
```

Development MinIO is optional:

```bash
docker compose --profile object-storage up --build
```

## Distributed worker leases

Translation, Vision and figure-render workers acquire an owner-specific Redis lease after dequeue. Leases use `SET NX EX`, renew through an owner-checked Lua heartbeat and release only when the same owner still holds the lease. A crashed worker stops renewing; the lease expires and normal recovery can resume the job. Duplicate dequeue/recovery attempts cannot execute the same job concurrently while the lease is alive.

Metrics:

```text
booktranslate_job_lease_conflicts_total{queue}
booktranslate_job_active_leases{queue}
```

## OpenTelemetry and SLO

When `OTEL_ENABLED=true`, API and worker processes export OTLP traces. HTTPX and SQLAlchemy are instrumented and API responses expose `X-Trace-ID` when a valid trace is active. Audit metadata links mutation events to the trace ID without recording request bodies.

Default SLO baseline:

```text
Availability     99.5%
p95 API latency  <= 1.0 s
```

`GET /api/ops/slo` returns the active targets and PromQL. The production baseline includes Prometheus rules for availability, p95 latency and sustained lease contention.

## Authentication and secrets

Application roles remain:

```text
admin | reviewer | translator | viewer
```

OIDC uses Authorization Code Flow with discovery, JWKS signature, issuer, audience, expiry and nonce validation. Application tokens are stored only as SHA-256 hashes.

Sensitive settings support `*_FILE` so production deployments can mount Docker/Kubernetes/external-secret values instead of exposing them directly in application environment variables. Supported file-backed values include database/Redis URLs, signing/bootstrap secrets, OIDC client secret, S3 credentials, provider keys and the metrics token.

Never commit provider keys, database credentials, OIDC secrets, TLS private keys or production `.env` files.

## Local run

```bash
cp .env.example .env
docker compose up --build
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Local defaults keep `AUTH_REQUIRED=false` and `STORAGE_BACKEND=local`.

Services:

- frontend: `http://localhost:3000`
- API / Swagger: `http://localhost:8000/docs`
- readiness: `http://localhost:8000/health`
- liveness: `http://localhost:8000/liveness`
- metrics: `http://localhost:8000/metrics`
- translation queue: `translation`
- Vision queue: `vision`
- figure-render queue: `figure-render`

## Production baseline

See [`deploy/README.md`](deploy/README.md).

The included production Compose stack provides:

- Nginx TLS termination and HTTP→HTTPS redirect;
- no public PostgreSQL, Redis, MinIO, backend or worker ports;
- mounted application secrets through `/run/secrets/*`;
- MinIO/S3-first application storage;
- separate translation, Vision and figure-render workers;
- Redis job leases;
- OTLP collector;
- Prometheus with protected internal scraping;
- security headers and public `/metrics` denial;
- Prometheus bound only to `127.0.0.1:9090`.

TLS material belongs in `deploy/tls/` and secret files in `deploy/secrets/`; both directories prevent credential/key files from being committed.

## Figure workflow in Workbench

The browser Workbench exposes:

```text
Run figure OCR
    ↓
translate/review figure_text segments
    ↓
Render translated figures
    ↓
Latest PNG preview/download
    ↓
DOCX / EPUB export
```

Completed translated figure variants are automatically embedded in translated document exports.

## API summary

### Authentication / users / SSO

```text
POST /api/auth/bootstrap
GET  /api/auth/me
GET  /api/auth/oidc/config
GET  /api/auth/oidc/login
GET  /api/auth/oidc/callback
POST /api/admin/users
GET  /api/admin/users
POST /api/admin/users/{user_id}/role
POST /api/admin/users/{user_id}/rotate-token
```

### Documents / Workbench / export

```text
POST /api/books
GET  /api/books
GET  /api/books/{book_id}
POST /api/books/upload
GET  /api/books/{book_id}/workbench
POST /api/translations/{translation_id}/editor-version
POST /api/books/{book_id}/export-ticket
GET  /api/books/{book_id}/export/docx
GET  /api/books/{book_id}/export/translated.docx
GET  /api/books/{book_id}/export/translated.epub
```

Supported source formats: `.docx`, `.epub`.

### Vision / OCR

```text
POST /api/books/{book_id}/vision-jobs
POST /api/assets/{asset_id}/vision-jobs
GET  /api/vision-jobs/{job_id}
GET  /api/books/{book_id}/vision-jobs
GET  /api/assets/{asset_id}/vision-extractions
```

### Translated figure rendering

```text
POST /api/books/{book_id}/figure-render-jobs
GET  /api/figure-render-jobs/{job_id}
GET  /api/books/{book_id}/figure-renders
POST /api/figure-renders/{render_id}/download-ticket
GET  /api/figure-renders/{render_id}/download
```

### Translation jobs

```text
POST /api/segments/{segment_id}/translate
POST /api/segments/{segment_id}/translate/pipeline
POST /api/books/{book_id}/translation-jobs
POST /api/chapters/{chapter_id}/translation-jobs
GET  /api/translation-jobs/{job_id}
GET  /api/books/{book_id}/translation-jobs
POST /api/translation-jobs/{job_id}/cancel
```

### QA / review

```text
POST /api/translations/{translation_id}/versions/{version_id}/qa
POST /api/translations/{translation_id}/versions/{version_id}/reviews
POST /api/human-reviews/{review_id}/resolve
GET  /api/reviews/inbox
POST /api/human-reviews/{review_id}/assign
POST /api/human-reviews/{review_id}/comments
GET  /api/translations/{translation_id}/versions/diff
POST /api/books/{book_id}/qa-report
GET  /api/books/{book_id}/qa-report/latest
```

### Operations

```text
GET /metrics
GET /api/ops/status
GET /api/ops/slo
GET /api/admin/audit-events
```

`/metrics` accepts either `X-Metrics-Token` or an equivalent Bearer credential, allowing Prometheus to use a mounted credentials file.

## Tests and CI

GitHub Actions now:

- starts real PostgreSQL and Redis;
- applies Alembic `0001 → 0009`;
- compiles backend, migrations and tests;
- validates local Compose and backup/restore shell syntax;
- validates the hardened production Compose with temporary non-secret CI placeholder files;
- runs `nginx -t` with an ephemeral self-signed certificate;
- tests local and mocked-S3 storage contracts;
- creates a real PNG, renders translated OCR text into it and verifies translated export asset substitution;
- verifies render idempotence;
- verifies owner-safe Redis lease acquire/renew/release behavior;
- verifies mounted secret-file overrides;
- retains all document, translation, QA, OIDC, Vision, audit and security tests from earlier stages;
- builds the Next.js production frontend.

CI performs no live LLM/Vision, production S3, OIDC provider or external telemetry calls and contains no real deployment credentials.

## Current boundaries

- DOCX/EPUB reconstruction is structural rather than pixel-identical.
- Vision bounding boxes are model outputs; publication-critical figures require human review.
- Figure redraw V1 uses bounded background replacement + text fitting, not semantic inpainting or vector-layout reconstruction.
- Rotated/curved/handwritten text is not specially rendered in V1.
- Generated figure variants are PNG even when the source asset used another raster format.
- S3/MinIO bucket lifecycle/versioning/replication policies belong to infrastructure configuration.
- The bundled OTLP collector uses a debug exporter by default; connect it to a durable tracing backend in production.
- The production Compose baseline is single-host. Horizontal autoscaling/HA should move PostgreSQL/object storage to managed services or a clustered deployment.
- Provider-specific rate-limit response headers are not yet fed back into the global scheduler.

## Next engineering stage

A future Stage 10 can focus on advanced figure inpainting/vector reconstruction, Kubernetes/Helm/autoscaling, provider-header-aware admission control, SCIM/session refresh management, event/webhook integrations and automated restore drills.
