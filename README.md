# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, translation memory, provider-neutral AI orchestration, durable workers, multi-model QA, human review and a browser translation workbench.

## Current status

### Stage 1 — Infrastructure ✅

- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL
- Redis
- Docker Compose
- readiness/liveness checks
- GitHub Actions CI

### Stage 2 — Document Engine V1 ✅

Persistent structure:

```text
Book
├── Asset
└── Chapter
    ├── Section
    │   └── Section
    └── Block
        ├── Segment
        ├── Figure -> Asset
        ├── DocumentTable
        └── Caption -> target Block
```

Implemented DOCX/EPUB parsing, chapter/section hierarchy, ordered paragraphs/lists/code/quotes, tables, figures, captions, deterministic segment hashes, PostgreSQL persistence and structural DOCX reconstruction.

### Stage 3 — Translation Engine V1 ✅

```text
Segment
└── Translation
    ├── TranslationVersion — translator
    ├── TranslationVersion — reviewer
    ├── TranslationVersion — critic/finalizer
    └── human-reviewed versions

ModelRun -> provider/model/prompt/tokens/latency/output/error
PromptVersion -> versioned prompt
Book -> GlossaryTerm
Book -> TranslationMemoryEntry
```

Implemented persistent version history, ModelRun audit trail, prompt versioning, glossary, exact-hash Translation Memory, Context Builder, provider-neutral Model Gateway and OpenAI/Kimi/Gemini/AITUNNEL adapters.

### Stage 4 — Jobs, Workers & Multi-model QA ✅

- durable book/chapter `TranslationJob`
- Redis FIFO queue and independent worker
- retries, idempotency, cancellation and stale-job recovery
- progress/current-segment tracking
- synthetic chapter/section heading segments
- multi-model QA with six deterministic dimensions
- translated DOCX export with safe structural fallbacks

### Stage 5 — Human Review, Book QA & Adaptive Routing ✅

- `HumanReview`: pending → approve/edit/reject
- human edits create auditable `TranslationVersion(role="human_reviewer")`
- automatic review requests below configurable QA threshold
- `BookQAReport` with deterministic 0–100 book score
- persistent terminology audit and `TerminologyIssue`
- `ProviderModelPolicy`
- `provider="auto"` with `priority` or `cheapest`
- Redis RPM/TPM/max-concurrency controls and fallback routing
- exact per-job token/cost telemetry
- input/output/cost budget gates including post-call overshoot enforcement

### Stage 6 — EPUB Fidelity & Translation Workbench ✅

```text
DOCX / EPUB
    ↓
Normalized blocks + inline fidelity metadata
    ├── hyperlinks
    ├── EPUB MathML
    ├── DOCX OMML
    └── footnote references
    ↓
Translation / Human Review
    ↓
Browser Workbench
    ├── chapters / segments
    ├── source ↔ target editor
    ├── QA dashboard
    ├── terminology issues
    └── human-version save
    ↓
Translated DOCX / EPUB
```

Implemented:

- translated EPUB reconstruction using the normalized persistent document model
- `GET /api/books/{book_id}/export/translated.epub`
- image/assets, headings, paragraphs, lists, code, quotes, captions and tables in EPUB output
- EPUB parser preservation of inline hyperlinks, MathML and footnote-reference metadata
- DOCX parser preservation of hyperlinks, OMML formula XML and footnote-reference IDs
- DOCX reconstruction restores external hyperlinks, OMML formulas and visible footnote markers where supported
- single workbench snapshot endpoint for browser editing
- direct human editor save that reuses the existing Human Review/version audit trail
- functional Next.js library/upload screen
- `/books/{book_id}` translator workspace
- chapter and segment navigation
- source/target dual editor
- segment QA status and review filters
- book-level QA dashboard
- terminology issue resolve/ignore actions
- translated DOCX and EPUB download actions

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

Verdicts:

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

The persisted report also contains low-quality segment count, unresolved reviews, terminology issues, model token totals and estimated cost.

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

Add only provider keys you actually use:

```env
OPENAI_API_KEY=
KIMI_API_KEY=
GEMINI_API_KEY=
AITUNNEL_API_KEY=
```

Never commit real API keys.

Services:

- frontend: `http://localhost:3000`
- Swagger: `http://localhost:8000/docs`
- readiness: `http://localhost:8000/health`
- liveness: `http://localhost:8000/liveness`

## API summary

### Documents and workbench

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

### Translation and jobs

```text
POST /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translation-context
POST /api/segments/{segment_id}/translate
POST /api/segments/{segment_id}/translate/pipeline
POST /api/translations/{translation_id}/versions/{version_id}/finalize
POST /api/books/{book_id}/translation-jobs
POST /api/chapters/{chapter_id}/translation-jobs
GET  /api/translation-jobs/{job_id}
GET  /api/books/{book_id}/translation-jobs
POST /api/translation-jobs/{job_id}/cancel
```

### QA, review and terminology

```text
POST /api/translations/{translation_id}/versions/{version_id}/qa
GET  /api/translations/{translation_id}/versions/{version_id}/qa
POST /api/translations/{translation_id}/versions/{version_id}/reviews
GET  /api/books/{book_id}/human-reviews
POST /api/human-reviews/{review_id}/resolve
POST /api/books/{book_id}/qa-report
GET  /api/books/{book_id}/qa-report/latest
GET  /api/books/{book_id}/terminology-issues
POST /api/terminology-issues/{issue_id}/status
```

### Adaptive routing

```text
POST   /api/ai/model-policies
GET    /api/ai/model-policies
DELETE /api/ai/model-policies/{policy_id}
GET    /api/ai/providers
```

Provider/model prices and capacity limits are deployment configuration and are intentionally not hard-coded.

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions:

- starts PostgreSQL and Redis
- applies the full Alembic chain through `0006`
- validates Document/Translation Engines
- validates Redis job processing and multi-model QA
- validates Stage 5 routing, human editing, book QA and budget gates
- validates Stage 6 routes and PostgreSQL workbench/human-editor behavior
- validates translated EPUB fidelity round trip
- builds the Next.js production frontend

No live LLM calls are made by CI.

## Current boundaries

- DOCX reconstruction is structural rather than pixel-identical.
- Stage 6 preserves hyperlink/formula/reference metadata, but full Word footnote/endnote body reconstruction still needs a dedicated note model.
- Translated inline anchor text cannot always be mapped safely to the translated sentence; EPUB therefore preserves link targets and source labels rather than inventing alignment.
- DOCX OMML is preserved as source formula XML; formulas are not sent through text translation.
- Translated tables are reconstructed only when the translated output preserves the original row/tab grid; otherwise source table structure is retained.
- Figures are preserved; OCR/vision translation of text embedded inside images is not yet a dedicated workflow.
- Terminology audit V1 is deterministic glossary matching rather than morphology-aware semantic analysis.
- Estimated monetary cost depends on configured policy prices and provider token telemetry.
- Redis RPM/TPM controls are application-side limits; production routing can later consume provider response headers and distributed leases.

## Next engineering stage

1. authentication and RBAC for translators/reviewers/admins;
2. dedicated footnote/endnote and hyperlink-span models for exact inline reconstruction;
3. OCR/vision workflow for text embedded in figures;
4. provider-header-aware distributed scheduling and stronger worker leases;
5. production deployment, observability, backup/restore and audit retention;
6. collaborative review features: comments, assignments and change comparison.
