# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, translation memory, provider-neutral AI orchestration, durable workers, multi-model QA and human review.

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

Persistent document model:

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

Implemented:

- DOCX and EPUB upload/parsing
- chapter/section hierarchy
- ordered paragraphs, lists, code and blockquotes
- tables, images/assets and captions
- deterministic segment SHA-256 hashes
- PostgreSQL persistence
- source DOCX Reconstruction Engine V1
- translated DOCX Reconstruction Engine
- parser/reconstruction and PostgreSQL round-trip tests

### Stage 3 — Translation Engine V1 ✅

```text
Segment
└── Translation (per target language)
    ├── TranslationVersion — translator
    ├── TranslationVersion — reviewer
    ├── TranslationVersion — critic/finalizer
    └── selected final version

ModelRun -> provider/model/prompt/tokens/latency/output/error
PromptVersion -> versioned prompt
Book -> GlossaryTerm
Book -> TranslationMemoryEntry
```

Implemented:

- immutable-style TranslationVersion history
- ModelRun audit trail
- versioned prompts
- per-book glossary
- exact-hash Translation Memory
- Context Builder with neighbouring source segments, glossary and memory
- provider-neutral Model Gateway
- OpenAI, Kimi, Gemini and AITUNNEL adapters
- configurable translator/reviewer/critic/finalizer pipeline
- provider tests with mocked HTTP transports

### Stage 4 — Translation Jobs, Workers & Multi-model QA ✅

```text
Book / Chapter
      ↓
TranslationJob (PostgreSQL source of truth)
      ↓
Redis queue signal
      ↓
translation-worker
      ↓
Translator → Reviewer → Critic → Finalizer
      ↓
final TranslationVersion
      ↓
QA evaluator A ─┐
QA evaluator B ─┼─> weighted score 0..100
QA evaluator C ─┘
      ↓
Translation Memory quality score
      ↓
Translated DOCX reconstruction
```

Implemented:

- book/chapter background jobs
- Redis FIFO queue and queued-ID deduplication
- independent Docker worker
- stale-running job recovery
- retries, idempotency and cancellation
- progress counters/current segment
- synthetic chapter/section heading segments
- multi-model TranslationQAResult persistence
- translated DOCX export with safe source fallbacks

### Stage 5 — Human Review, Book QA & Adaptive Routing ✅

```text
Model policies
   ├── priority / cost
   ├── RPM / TPM
   └── max concurrency
          ↓
provider="auto"
          ↓
rate-limit-aware route selection
          ↓
ModelRun tokens + estimated cost
          ↓
TranslationJob budget gates
          ↓
Multi-model QA
    ┌─────┴───────────┐
    ↓                 ↓
Human Review       Book QA
approve/edit/reject   ├── coverage
                      ├── translation quality
                      ├── terminology consistency
                      ├── review coverage
                      └── tokens / estimated cost
```

Implemented:

- `HumanReview` workflow: pending → approve / edit / reject
- human editing creates a new auditable `TranslationVersion` with role `human_reviewer`
- automatic human-review requests below a configurable QA threshold
- `BookQAReport` with an explicit 0–100 book-level score
- whole-book terminology audit against approved glossary terms
- persisted `TerminologyIssue` records with open/resolved/ignored lifecycle
- `ProviderModelPolicy` for provider/model priority and roles
- configurable input/output price per 1M tokens; no provider price is hard-coded
- Redis-backed requests-per-minute, tokens-per-minute and max-concurrency controls
- `provider="auto"` selection with `priority` or `cheapest` routing strategy
- fallback to another eligible model policy when a higher-priority route has no capacity
- exact per-job linkage from `ModelRun` to `TranslationJob`
- actual input/output token telemetry when returned by the provider
- estimated USD cost derived from configured policy prices and actual token counts
- hard job limits for estimated cost, input tokens and output tokens
- post-call budget gate: if a final in-flight request pushes the job over budget, the job becomes `budget_exceeded`
- book QA cost/token totals derived from persisted ModelRuns

## Quality scoring

### Segment QA

Each QA evaluator returns six values from 0 to 100. BookTranslate AI computes its score deterministically:

```text
Semantic accuracy       30%
Terminology             20%
Completeness            15%
Fluency                 15%
Technical integrity     10%
Style                   10%
```

Multiple evaluator scores are combined using configured evaluator weights.

```text
90–100  excellent
80–89   good
70–79   acceptable
60–69   needs_review
<60     poor
```

### Book QA

Current deterministic book-level score:

```text
Translation coverage       25%
Average segment QA         40%
Terminology consistency    25%
Human review coverage      10%
```

The persisted report also includes low-quality segment count, unresolved reviews, terminology issues, total model tokens and estimated cost.

## Run

Copy the environment template:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Add only provider keys you intend to use:

```env
OPENAI_API_KEY=
KIMI_API_KEY=
GEMINI_API_KEY=
AITUNNEL_API_KEY=
```

Never commit real API keys.

Start all services:

```bash
docker compose up --build
```

Services include frontend, FastAPI backend, PostgreSQL, Redis and the translation worker. The backend applies `alembic upgrade head` before becoming healthy.

Useful endpoints:

- Frontend: `http://localhost:3000`
- Swagger: `http://localhost:8000/docs`
- Readiness: `http://localhost:8000/health`
- Liveness: `http://localhost:8000/liveness`

## API summary

### Documents

```text
POST /api/books
GET  /api/books
GET  /api/books/{book_id}
POST /api/books/upload
GET  /api/books/{book_id}/export/docx
GET  /api/books/{book_id}/export/translated.docx
```

Supported source formats: `.docx`, `.epub`.

### Glossary

```text
POST /api/books/{book_id}/glossary
GET  /api/books/{book_id}/glossary
```

### Segment translation

```text
POST /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translation-context
POST /api/segments/{segment_id}/translate
POST /api/segments/{segment_id}/translate/pipeline
POST /api/translations/{translation_id}/versions/{version_id}/finalize
GET  /api/ai/providers
```

Explicit `provider/model` requests remain supported. To use adaptive routing, send `provider: "auto"` and configure model policies first.

### Translation jobs

```text
POST /api/books/{book_id}/translation-jobs
POST /api/chapters/{chapter_id}/translation-jobs
GET  /api/translation-jobs/{job_id}
GET  /api/books/{book_id}/translation-jobs
POST /api/translation-jobs/{job_id}/cancel
```

Example adaptive whole-book configuration:

```json
{
  "target_language": "ru",
  "stages": [
    {"provider": "auto", "model": null, "role": "translator", "routing_strategy": "priority"},
    {"provider": "auto", "model": null, "role": "reviewer", "routing_strategy": "priority"},
    {"provider": "auto", "model": null, "role": "finalizer", "routing_strategy": "priority"}
  ],
  "qa_evaluators": [
    {"provider": "auto", "model": null, "weight": 1.0, "routing_strategy": "cheapest"}
  ],
  "human_review_below": 85,
  "max_job_cost_usd": 25,
  "max_job_input_tokens": 2000000,
  "max_job_output_tokens": 500000,
  "max_retries": 2,
  "idempotency_key": "book-42-ru-v2"
}
```

### Model routing policies

```text
POST   /api/ai/model-policies
GET    /api/ai/model-policies
DELETE /api/ai/model-policies/{policy_id}
```

A policy can define:

- provider/model
- enabled flag
- routing priority
- allowed roles
- input/output cost per 1M tokens
- requests per minute
- tokens per minute
- max concurrency

Prices and capacity limits are deployment configuration. They are intentionally not hard-coded because provider prices and account limits can change.

### QA and human review

```text
POST /api/translations/{translation_id}/versions/{version_id}/qa
GET  /api/translations/{translation_id}/versions/{version_id}/qa
POST /api/translations/{translation_id}/versions/{version_id}/reviews
GET  /api/books/{book_id}/human-reviews
POST /api/human-reviews/{review_id}/resolve
```

### Book QA and terminology

```text
POST /api/books/{book_id}/qa-report
GET  /api/books/{book_id}/qa-report/latest
GET  /api/books/{book_id}/terminology-issues
POST /api/terminology-issues/{issue_id}/status
```

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions:

- starts PostgreSQL and Redis
- applies the full Alembic chain through `0006`
- runs Document Engine round-trip tests
- runs Translation Engine version/history/memory tests
- runs Redis job integration tests
- runs Stage 4 batch + QA tests
- runs Stage 5 routing fallback, exact job-cost telemetry, human-edit review and book QA tests
- tests final-segment budget enforcement
- validates provider adapters without live credentials
- builds the Next.js frontend

No live LLM calls are made by CI.

## Current boundaries

- DOCX reconstruction is structural rather than pixel-identical.
- Formulas, footnotes/endnotes, complex hyperlinks and advanced style fidelity still need dedicated document models.
- Translated tables are reconstructed only when the translated output preserves the original row/tab grid; otherwise the original table is retained.
- Figures are preserved; image text/alt-text translation is not yet a dedicated vision workflow.
- Terminology audit V1 uses deterministic glossary-term matching; morphology-aware/semantic terminology analysis can be added later.
- Estimated monetary cost is only as accurate as configured policy prices and token usage returned by providers.
- A hard budget can be exceeded by one already in-flight model request because its final token usage is only known after the response; the post-call gate immediately stops further work and marks the job `budget_exceeded`.
- Redis RPM/TPM controls are local application-side limits. Future production routing can additionally consume provider rate-limit response headers and use distributed leases.

## Next engineering stage

1. translated EPUB reconstruction/export;
2. formula, footnote/endnote and hyperlink fidelity;
3. authenticated users/RBAC for human reviewers and administrators;
4. frontend book QA/review dashboard;
5. stronger distributed worker leases and provider-header-aware scheduling;
6. OCR/vision workflow for text embedded in figures;
7. production deployment, observability and backup/restore hardening.
