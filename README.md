# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent DOCX/EPUB reconstruction, provider-neutral AI orchestration, durable workers, multi-model QA, human review, Vision/OCR, translated figure reconstruction, SSO/SCIM, object storage and production deployment tooling.

## Current status

- **Stage 1 — Infrastructure ✅** Next.js + TypeScript, FastAPI, PostgreSQL, Redis, Docker Compose, health checks and CI.
- **Stage 2 — Document Engine ✅** `Book → Chapter → Section → Block → Segment`, assets, figures, tables, captions, DOCX/EPUB parsing and reconstruction.
- **Stage 3 — Translation Engine ✅** Translation history, ModelRun audit, prompts, glossary, Translation Memory, Context Builder and OpenAI/Kimi/Gemini/AITUNNEL gateway.
- **Stage 4 — Jobs, Workers & Multi-model QA ✅** durable Redis jobs, retries/recovery, progress, multi-model QA and translated DOCX.
- **Stage 5 — Human Review, Book QA & Routing ✅** approval/edit/reject, terminology audit, provider policies, budgets and application rate controls.
- **Stage 6 — EPUB Fidelity & Translator Workbench ✅** translated EPUB, hyperlink/formula fidelity metadata, browser editor and QA dashboard.
- **Stage 7 — Notes, RBAC & Reviewer Workflow ✅** footnote/endnote translation, roles, assignments, comments, version diff and reviewer inbox.
- **Stage 8 — Vision/OCR, SSO, Security & Operations ✅** figure OCR, OIDC, API perimeter, signed downloads, Prometheus, audit and backup/restore.
- **Stage 9 — Figure Redraw, S3/MinIO & Telemetry ✅** translated figure variants, distributed leases, OpenTelemetry/SLO and TLS production Compose.
- **Stage 10 — Inpainting, Adaptive Scheduling, SCIM & Kubernetes ✅** OpenCV image reconstruction, vector SVG sidecars, provider feedback-aware routing, rotating browser sessions, SCIM 2.0, Helm/KEDA, restore drills and versioned release/deployment workflows.

## End-to-end architecture

```text
DOCX / EPUB
    ↓
Document Engine
    ↓
Book → Chapter → Section → Block → Segment
    ↓
Translation Memory + Glossary + Context Builder
    ↓
Adaptive Model Router
    ├─ static priority/cost/RPM/TPM/concurrency
    └─ provider feedback: remaining quota / reset / Retry-After cooldown
    ↓
Translator → Reviewer → Critic → Finalizer
    ↓
Multi-model QA → Human Review
    ↓
Translated DOCX / EPUB

Figure Asset (immutable)
    ↓
Vision/OCR → figure_text + normalized bbox
    ↓
Translation / QA / Human Review
    ↓
FigureRenderJob
    ├─ overlay
    ├─ OpenCV Telea inpaint
    └─ vector: inpainted PNG + editable SVG text layer
    ↓
S3 / MinIO / LocalStorage
    ↓
Translated document export
```

## Advanced translated figures

`POST /api/books/{book_id}/figure-render-jobs` accepts:

```json
{"render_mode":"overlay"}
{"render_mode":"inpaint"}
{"render_mode":"vector"}
```

`overlay` preserves the Stage 9 bounded background replacement renderer. `inpaint` creates an OCR-region mask and reconstructs the background with OpenCV Telea before fitting translated text. `vector` uses the same cleaned background, produces the compatible translated PNG and stores an editable SVG sidecar whose text remains vector text.

The source asset is never overwritten. Render fingerprints include source SHA-256, target language, render mode, segment hashes, translations and bounding boxes, so identical reruns are idempotent.

Vector API:

```text
POST /api/figure-renders/{render_id}/vector-download-ticket
GET  /api/figure-renders/{render_id}/vector-download
```

## Provider-feedback-aware adaptive routing

The router still enforces configured model policy, priority, cost, RPM, TPM and concurrency. Stage 10 also normalizes provider response headers such as remaining request/token capacity, reset durations and `Retry-After`.

```text
Provider response
    ↓
normalized rate-limit feedback
    ↓
short-lived Redis provider/model state
    ↓
capacity / cooldown admission check
    ↓
adaptive candidate selection
```

Successful responses update capacity feedback. HTTP 429 / Retry-After responses put only the affected provider/model into a temporary cooldown; other configured models remain eligible.

## Browser sessions, OIDC and SCIM

OIDC no longer rotates a single user-wide application token. A browser login creates an independent `UserSession` with:

- short-lived access token;
- rotating refresh token;
- independent expiry/revocation;
- user-agent/IP audit metadata;
- configurable maximum active sessions per user.

Refresh-token rotation uses a PostgreSQL row lock so one old refresh token cannot be successfully rotated by two concurrent requests.

Session API:

```text
POST   /api/auth/session/refresh
GET    /api/auth/sessions
DELETE /api/auth/sessions/{session_id}
POST   /api/auth/sessions/revoke-all
```

SCIM 2.0 is independently protected by `SCIM_BEARER_TOKEN` and supports user provisioning/deprovisioning and deterministic BookTranslate role groups:

```text
GET    /scim/v2/ServiceProviderConfig
GET    /scim/v2/ResourceTypes
GET    /scim/v2/Schemas
GET    /scim/v2/Users
POST   /scim/v2/Users
GET    /scim/v2/Users/{id}
PUT    /scim/v2/Users/{id}
PATCH  /scim/v2/Users/{id}
DELETE /scim/v2/Users/{id}
GET    /scim/v2/Groups
GET    /scim/v2/Groups/{id}
PATCH  /scim/v2/Groups/{id}
```

SCIM deactivation revokes the affected user's active browser sessions. Roles remain:

```text
admin | reviewer | translator | viewer
```

## Storage

The application uses a provider-neutral async contract:

```text
StorageBackend
├─ LocalStorage
└─ S3Storage → AWS S3 / MinIO / S3-compatible stores
```

Local remains the development default. Production can use S3-compatible storage for source documents, parsed assets and generated figure variants. Native S3 presigned downloads are explicit opt-in; private MinIO can stay behind application signed-ticket proxy downloads.

## Local run

```bash
cp .env.example .env
docker compose up --build
```

Optional development MinIO:

```bash
docker compose --profile object-storage up --build
```

Services:

- frontend: `http://localhost:3000`
- API / Swagger: `http://localhost:8000/docs`
- readiness: `http://localhost:8000/health`
- liveness: `http://localhost:8000/liveness`
- metrics: `http://localhost:8000/metrics`
- translation queue: `booktranslate:queue:translation`
- Vision queue: `booktranslate:queue:vision`
- figure render queue: `booktranslate:queue:figure-render`

## Production targets

### Single host

See [`deploy/README.md`](deploy/README.md). The production Compose baseline provides TLS Nginx, private PostgreSQL/Redis/MinIO/backend/workers, mounted secrets, Prometheus and OTLP collector.

### Kubernetes / Helm

See [`deploy/helm/booktranslate/README.md`](deploy/helm/booktranslate/README.md).

The Helm chart deploys stateless application components and expects external PostgreSQL, Redis and S3-compatible object storage. It includes:

- Alembic `pre-install,pre-upgrade` migration Job;
- backend/frontend Deployments and Services;
- independent translation, Vision and figure-render worker Deployments;
- HPA for API/frontend;
- optional KEDA Redis-list queue autoscaling for workers;
- PodDisruptionBudgets;
- ingress-only NetworkPolicy;
- TLS Ingress routing for `/api`, `/scim` and frontend;
- optional authenticated Prometheus `ServiceMonitor`;
- externally managed Kubernetes Secret only — the chart does not create production credentials.

Example validation:

```bash
helm lint deploy/helm/booktranslate
helm template booktranslate deploy/helm/booktranslate
helm template booktranslate deploy/helm/booktranslate \
  --set keda.enabled=true \
  --set-string keda.redisAddress=redis.example.internal:6379
```

## Release and deployment automation

`.github/workflows/release.yml` publishes a versioned release from a `v*` tag or explicit manual version:

```text
validate version + Helm
    ↓
build backend/frontend
    ↓
GHCR images + provenance + SBOM
    ↓
OCI Helm chart + SHA-256
    ↓
GitHub Release
```

`.github/workflows/deploy-production.yml` is manual and bound to the protected GitHub `production` environment. It requires an external `KUBE_CONFIG_B64`, pulls a previously published OCI chart and runs `helm upgrade --install --atomic --wait`. Cluster credentials are never stored in the repository.

## Restore drills

Normal backup/restore scripts cover PostgreSQL, Redis and persistent uploaded/generated files. Stage 10 adds `scripts/restore_drill.sh`, which performs a destructive verification:

1. create independent PostgreSQL, Redis and file markers;
2. create a backup;
3. destroy all three live markers;
4. restore the backup;
5. verify all three markers reappear;
6. clean up drill state.

`.github/workflows/restore-drill.yml` can run manually and is scheduled weekly. It uploads restore evidence and tears down the isolated local recovery stack after the test.

## Observability and availability

OpenTelemetry instruments API, HTTPX and SQLAlchemy. API responses expose `X-Trace-ID` when tracing is active, while audit records link mutation events to trace IDs without storing request bodies.

Default SLO baseline:

```text
Availability     99.5%
p95 API latency  <= 1.0 s
```

Workers use owner-specific Redis leases with TTL/heartbeat/recovery. Prometheus exposes HTTP, queue-lease and SLO signals.

## Database migrations

Latest migration:

```text
20260813_0010
```

It adds:

- `user_sessions`;
- `app_users.scim_external_id` and `scim_managed`;
- `figure_renders.render_mode`;
- `figure_render_jobs.render_mode`.

## CI contract

Every feature/main CI run validates:

- real PostgreSQL and Redis;
- Python compileall;
- Alembic `0001 → 0010`;
- local Docker Compose;
- backup/restore/restore-drill shell syntax;
- production Compose with temporary CI-only placeholder secret files;
- Nginx syntax with an ephemeral self-signed TLS certificate;
- Helm lint/template without KEDA;
- Helm template with KEDA and real BookTranslate queue names;
- complete backend pytest suite including sessions, SCIM, provider cooldown routing and OpenCV/vector rendering;
- Next.js production build.

CI makes no live LLM/Vision call and does not use production S3, real OIDC/SCIM identity providers, production TLS private keys, Kubernetes credentials or real deployment secrets.

## Important boundaries

- DOCX/EPUB reconstruction is structural rather than pixel-identical.
- OCR bounding boxes remain model-derived; publication-critical figures require human review.
- Inpainting V1 is deterministic OpenCV Telea region reconstruction, not generative semantic image synthesis.
- SVG vector mode preserves translated text as vector text but does not reconstruct arbitrary original vector primitives or complex typographic geometry.
- Rotated, curved and handwritten text are not specially typeset.
- SCIM V1 covers application users and BookTranslate role groups; enterprise directory extensions/entitlements beyond this model are not implemented.
- Kubernetes stateful dependencies are intentionally external. HA, backups, replication and lifecycle controls for PostgreSQL/Redis/S3 belong to infrastructure configuration.
- Release/deploy workflows are production-ready automation foundations, but an actual deployment still requires real registry/cluster/secret-manager configuration outside this repository.
