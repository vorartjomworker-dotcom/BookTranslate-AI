# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, provider-neutral AI orchestration, durable workers, multi-model QA, human review, figure Vision/OCR, SSO/RBAC and browser translation/reviewer workspaces.

## Current status

### Stage 1 — Infrastructure ✅
Next.js + TypeScript, FastAPI, PostgreSQL, Redis, Docker Compose, health checks and GitHub Actions CI.

### Stage 2 — Document Engine ✅
Persistent `Book → Chapter → Section → Block → Segment` structure with assets, figures, tables and captions; DOCX/EPUB parsing, deterministic hashes and structural reconstruction.

### Stage 3 — Translation Engine ✅
Persistent Translation/TranslationVersion history, ModelRun audit trail, prompts, glossary, Translation Memory, Context Builder and OpenAI/Kimi/Gemini/AITUNNEL gateway.

### Stage 4 — Jobs, Workers & Multi-model QA ✅
Durable book/chapter translation jobs, Redis worker, retries/idempotency/recovery, progress, multi-model QA and translated DOCX.

### Stage 5 — Human Review, Book QA & Adaptive Routing ✅
Human approve/edit/reject, auditable human versions, book QA 0–100, terminology audit, provider policies, token/cost budgets and Redis RPM/TPM/concurrency routing.

### Stage 6 — EPUB Fidelity & Translator Workbench ✅
Translated EPUB, hyperlink/MathML/OMML fidelity, browser library/workbench, source↔target editor, QA dashboard and terminology actions.

### Stage 7 — Notes, RBAC & Reviewer Workflow ✅
First-class DOCX/EPUB footnote/endnote translation, application roles (`admin`, `reviewer`, `translator`, `viewer`), reviewer assignment, comments, version diff and reviewer inbox.

### Stage 8 — Vision/OCR, SSO, Security & Operations ✅

```text
Figure Asset
    ↓
VisionJob (Redis)
    ↓
Vision Provider
    ↓
VisionExtraction
    ↓
OCR regions + bbox
    ↓
Segment(type=figure_text)
    ↓
Translation → QA → Human Review

OIDC Provider
    ↓ auth code + state + nonce
JWKS signature / issuer / audience validation
    ↓
AppUser + local hashed app token
    ↓
Full /api/* security perimeter
    ↓
Signed short-lived download ticket

HTTP request
    ↓
Request ID + Prometheus metrics + mutation audit
```

Implemented:

- durable `VisionJob` and independent `vision-worker` backed by Redis;
- OpenAI Vision adapter using the Responses API with image input;
- image bytes are read from persisted assets and sent as data URLs; no OCR-specific binary is required;
- OCR output is normalized into text regions with optional normalized bounding boxes and region kinds;
- `VisionExtraction` persists extracted text, regions, provider/model, provider request ID, token telemetry and failures;
- each figure text region becomes an auditable `Segment(type="figure_text")`, therefore it uses the existing Translation → QA → Human Review pipeline;
- repeat OCR marks obsolete figure-text segments `superseded`; translation jobs skip superseded segments;
- source figure pixels are not silently modified;
- generic confidential-client OpenID Connect Authorization Code flow;
- discovery, token exchange, JWKS signature validation, issuer, audience, expiry and nonce checks;
- explicitly unverified OIDC email identities are rejected;
- configurable OIDC role claim with safe fallback to `viewer`;
- OIDC users are bound to issuer + subject and receive a local application token whose SHA-256 hash is persisted;
- full `/api/*` perimeter when `AUTH_REQUIRED=true`, with only bootstrap/OIDC login endpoints public;
- short-lived HMAC-SHA256 signed download tickets bound to an exact export path;
- translator Workbench requests signed download URLs instead of exposing bearer tokens in browser download navigation;
- per-request `X-Request-ID`;
- Prometheus request counter, latency histogram and in-progress gauge;
- `/metrics` protected by a separate metrics token in authenticated deployments;
- mutation audit log (`POST`, `PUT`, `PATCH`, `DELETE`) without storing request bodies or secrets;
- admin operations status and audit-event APIs;
- PostgreSQL + Redis + uploaded-assets backup/restore scripts for Bash and PowerShell;
- Docker `restart: unless-stopped`, worker grace periods and separate Vision worker;
- Alembic `0008` for OIDC identity fields, Vision jobs/extractions and audit events.

## Quality scoring

### Segment QA

```text
Semantic accuracy       30%
Terminology             20%
Completeness            15%
Fluency                 15%
Technical integrity     10%
Style                   10%
```

```text
90–100  excellent
80–89   good
70–79   acceptable
60–69   needs_review
<60     poor
```

### Book QA

```text
Translation coverage       25%
Average segment QA         40%
Terminology consistency    25%
Human review coverage      10%
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Never commit provider, bootstrap, signing, OIDC or metrics secrets.

### Local development

```env
AUTH_REQUIRED=false
OPENAI_API_KEY=
VISION_MODEL=
```

### Protected deployment

Use strong independent secrets:

```env
AUTH_REQUIRED=true
BOOTSTRAP_ADMIN_TOKEN=<one-time-admin-bootstrap-secret>
AUTH_SIGNING_SECRET=<download-and-state-signing-secret>
METRICS_TOKEN=<metrics-scrape-secret>
CORS_ORIGINS=https://translator.example.com
```

Create the first administrator through `POST /api/auth/bootstrap` with `X-Bootstrap-Token`. The returned application token is displayed once; only its SHA-256 hash is stored.

### Generic OIDC / SSO

```env
OIDC_ENABLED=true
OIDC_ISSUER=https://idp.example.com
OIDC_CLIENT_ID=<client-id>
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://api.example.com/api/auth/oidc/callback
OIDC_FRONTEND_REDIRECT_URI=https://translator.example.com/auth/callback
OIDC_ROLE_CLAIM=booktranslate_role
OIDC_DEFAULT_ROLE=viewer
```

The frontend can also use locally issued application tokens; SSO and local bearer tokens map to the same application-role model.

### Figure Vision/OCR

```env
OPENAI_API_KEY=<provider-secret>
VISION_PROVIDER=openai
VISION_MODEL=<deployment-selected-vision-capable-model>
```

`VISION_MODEL` is intentionally deployment-configured rather than hard-coded.

Services:

- frontend: `http://localhost:3000`
- API / Swagger: `http://localhost:8000/docs`
- readiness: `http://localhost:8000/health`
- liveness: `http://localhost:8000/liveness`
- Prometheus: `http://localhost:8000/metrics`
- translation worker: Redis queue `translation`
- vision worker: Redis queue `vision`

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

### QA / reviewer workflow

```text
POST /api/translations/{translation_id}/versions/{version_id}/qa
GET  /api/translations/{translation_id}/versions/{version_id}/qa
POST /api/translations/{translation_id}/versions/{version_id}/reviews
GET  /api/books/{book_id}/human-reviews
POST /api/human-reviews/{review_id}/resolve
GET  /api/reviews/inbox
POST /api/human-reviews/{review_id}/assign
POST /api/human-reviews/{review_id}/comments
GET  /api/human-reviews/{review_id}/comments
POST /api/review-comments/{comment_id}/resolve
GET  /api/translations/{translation_id}/versions/diff
POST /api/books/{book_id}/qa-report
GET  /api/books/{book_id}/qa-report/latest
```

### Operations

```text
GET /metrics
GET /api/ops/status
GET /api/admin/audit-events
```

## Backup / restore

Backups contain PostgreSQL, Redis state and `/data/uploads` (source uploads, extracted assets and generated exports).

Linux/macOS:

```bash
./scripts/backup.sh
./scripts/restore.sh ./backups/<timestamp>
```

PowerShell:

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupDirectory .\backups\<timestamp>
```

For production, move backups off-host and encrypt them with infrastructure-level key management. Test restore procedures regularly; a backup is not operationally useful until restore is verified.

## Tests and CI

GitHub Actions:

- starts real PostgreSQL and Redis services;
- applies Alembic `0001 → 0008`;
- runs Python compile validation;
- validates Bash backup/restore syntax and `docker compose config`;
- tests all Stage 1–7 document/translation/reviewer behavior;
- tests OpenAI Vision request schema with mocked HTTP transport;
- tests VisionJob → VisionExtraction → `figure_text` DB integration;
- tests full authenticated API perimeter and signed browser download tickets;
- tests OIDC discovery/token/JWKS/issuer/audience/nonce provisioning using an ephemeral RSA signing key and mocked identity provider;
- tests Prometheus metrics protection and mutation audit persistence;
- builds the Next.js production frontend including SSO callback and protected download workflow.

CI never makes a live LLM/OCR call and contains no real API/OIDC credentials.

## Current boundaries

- DOCX/EPUB reconstruction is structural rather than pixel-identical.
- Word note bodies support translated textual content; deeply nested tables/images inside notes are still flattened.
- Vision/OCR extracts and translates text regions but does **not** redraw translated text into source image pixels yet.
- The Vision provider interface is extensible, but Stage 8 ships an OpenAI image-input implementation first.
- Vision accuracy and bounding boxes are model outputs and must be reviewed for publication-critical figures.
- OIDC V1 is a generic confidential-client Authorization Code integration, not provider-specific enterprise provisioning/SCIM.
- OIDC login rotates the local application token for that user; multi-session refresh-token management is not implemented yet.
- Download tickets are application-signed and short-lived; object-storage-native signed URLs are preferable once assets move to S3/MinIO.
- Mutation audit intentionally excludes request bodies to avoid accidental secret/content capture.
- The included backup scripts are operational foundations; production backups should be encrypted, scheduled, monitored and stored off-host.
- Redis RPM/TPM controls remain application-side; provider-header-aware scheduling and stronger distributed leases can be added later.

## Next engineering stage

Recommended Stage 9:

1. image-redraw/overlay pipeline that renders translated OCR regions back into a derived figure while retaining the immutable source image;
2. S3/MinIO object storage with native signed object URLs and lifecycle policies;
3. production deployment IaC, reverse proxy/TLS and secrets manager integration;
4. OpenTelemetry distributed traces, alerting and SLO dashboards;
5. scheduled encrypted off-host backups with automated restore drills;
6. stronger distributed worker leases and provider-header-aware rate-limit scheduling.
