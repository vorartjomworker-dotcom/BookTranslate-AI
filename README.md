# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, translation memory, provider-neutral AI orchestration, durable workers, multi-model QA, human review and browser translation/reviewer workspaces.

## Current status

### Stage 1 — Infrastructure ✅
- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL + Redis
- Docker Compose
- readiness/liveness checks
- GitHub Actions CI

### Stage 2 — Document Engine ✅
Persistent `Book → Chapter → Section → Block → Segment` structure with assets, figures, tables and captions; DOCX/EPUB parsing; deterministic hashes; PostgreSQL persistence; structural reconstruction.

### Stage 3 — Translation Engine ✅
Persistent `Translation` / `TranslationVersion` history, `ModelRun` audit trail, prompt versioning, glossary, Translation Memory, Context Builder and provider-neutral OpenAI/Kimi/Gemini/AITUNNEL gateway.

### Stage 4 — Jobs, Workers & Multi-model QA ✅
Durable book/chapter jobs, Redis worker, retries/idempotency/cancellation/recovery, progress tracking, synthetic heading segments, deterministic multi-model QA and translated DOCX export.

### Stage 5 — Human Review, Book QA & Adaptive Routing ✅
Human approve/edit/reject workflow, auditable human versions, book QA 0–100, terminology audit, provider policies, `provider="auto"`, Redis RPM/TPM/concurrency controls, exact token/cost telemetry and job budget gates.

### Stage 6 — EPUB Fidelity & Translator Workbench ✅
Translated EPUB export, hyperlink/MathML/OMML fidelity metadata, translator library/workbench, source↔target editor, Book QA dashboard, terminology actions and auditable manual editor versions.

### Stage 7 — Notes, RBAC & Reviewer Workflow ✅

```text
DOCX / EPUB
   ↓
Footnote / Endnote bodies
   ↓
Block(type=footnote|endnote)
   ↓
Segment
   ↓
Translator → QA → Human Review
   ↓
Translated note body
   ↓
Real DOCX note part / semantic EPUB aside

Bearer token
   ↓
AppUser: admin | reviewer | translator | viewer
   ↓
Reviewer assignment + priority
   ↓
Comments + version diff
   ↓
Approve / Edit / Reject
```

Implemented:

- real DOCX `word/footnotes.xml` and `word/endnotes.xml` body extraction;
- note bodies become ordinary translatable `Block`/`Segment` units, so they pass through the same translation, QA and Human Review pipeline;
- real DOCX reconstruction with `w:footnoteReference`, `w:endnoteReference`, note relationships, content types and translated note parts;
- semantic EPUB `<aside epub:type="footnote|endnote">` import/export;
- `AppUser` persistence with roles `admin`, `reviewer`, `translator`, `viewer`;
- Bearer API tokens stored only as SHA-256 hashes;
- optional production auth via `AUTH_REQUIRED=true` while local development remains compatible with `AUTH_REQUIRED=false`;
- one-time first-admin bootstrap using `BOOTSTRAP_ADMIN_TOKEN`;
- administrator user creation, role/active-state management and token rotation;
- reviewer assignment and review priority;
- reviewer inbox with assigned/unassigned queue filtering;
- persistent reviewer comments;
- translation-version comparison using word-level diff and similarity score;
- reviewer browser page at `/reviews`;
- translator Workbench uses the same browser Bearer-token session;
- Alembic `0007` for users, reviewer assignment and comments.

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

Provider keys remain optional and must never be committed:

```env
OPENAI_API_KEY=
KIMI_API_KEY=
GEMINI_API_KEY=
AITUNNEL_API_KEY=
```

Local development defaults to:

```env
AUTH_REQUIRED=false
BOOTSTRAP_ADMIN_TOKEN=
```

For a protected deployment, set a strong one-time bootstrap secret and enable authentication:

```env
AUTH_REQUIRED=true
BOOTSTRAP_ADMIN_TOKEN=<deployment-secret>
```

Then create the first administrator with `POST /api/auth/bootstrap` and pass the deployment secret in `X-Bootstrap-Token`. The returned administrator API token is shown once; only its SHA-256 hash is persisted.

Services:
- frontend: `http://localhost:3000`
- Swagger: `http://localhost:8000/docs`
- readiness: `http://localhost:8000/health`
- liveness: `http://localhost:8000/liveness`

## API summary

### Authentication / users
```text
POST /api/auth/bootstrap
GET  /api/auth/me
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
GET  /api/books/{book_id}/export/docx
GET  /api/books/{book_id}/export/translated.docx
GET  /api/books/{book_id}/export/translated.epub
```

Supported source formats: `.docx`, `.epub`.

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

### Routing / terminology
```text
POST   /api/ai/model-policies
GET    /api/ai/model-policies
DELETE /api/ai/model-policies/{policy_id}
GET    /api/ai/providers
GET    /api/books/{book_id}/terminology-issues
POST   /api/terminology-issues/{issue_id}/status
```

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions:

- starts PostgreSQL and Redis;
- applies the full Alembic chain through `0007`;
- validates document/translation engines, jobs, multi-model QA, routing, budgets and human review;
- validates translated EPUB fidelity;
- validates real DOCX footnote/endnote parts and round-trip note parsing/segmentation;
- validates semantic EPUB notes;
- validates Stage 7 token authentication, reviewer assignment, inbox, comments and version comparison;
- builds the Next.js production frontend, including translator and reviewer workspaces.

No live LLM calls or real provider credentials are used by CI.

## Current boundaries

- DOCX/EPUB reconstruction is structural rather than pixel-identical.
- Note bodies are now first-class translated content, but complex nested note content such as tables/images inside a Word note is still flattened to note text.
- Authentication V1 is application Bearer-token RBAC, not OAuth/OIDC/SSO; production SSO can replace the token authenticator without changing application roles.
- Export download endpoints remain direct-download compatible; a hardened multi-tenant deployment should add signed/protected downloads or authenticated blob delivery.
- Translated inline anchor text cannot always be aligned safely to rewritten translated sentences; link target preservation is preferred over invented span alignment.
- OMML/MathML formulas are preserved as formula markup and are not sent through ordinary natural-language translation.
- OCR/vision translation for text embedded inside figures is not yet implemented.
- Terminology audit V1 is deterministic glossary matching rather than morphology-aware semantic analysis.
- Redis RPM/TPM controls are application-side; production scheduling can additionally consume provider rate-limit headers and distributed leases.

## Next engineering stage

Stage 8 should focus on OCR/vision figure translation, production OAuth/OIDC/SSO and protected downloads, stronger distributed worker leases/provider-header-aware scheduling, observability/audit retention, backup/restore and production deployment hardening.
