# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, translation memory, provider-neutral AI orchestration and multi-model QA.

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
- `GET /api/books/{book_id}/export/docx`
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

- persistent Translation/TranslationVersion history
- ModelRun audit trail
- versioned prompts
- per-book glossary
- exact-hash Translation Memory
- Context Builder with neighbouring source segments, glossary and memory
- provider-neutral Model Gateway
- OpenAI, Kimi, Gemini and AITUNNEL adapters
- configurable translator/reviewer/critic/finalizer pipeline
- provider tests with mocked HTTP transports
- PostgreSQL integration coverage

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
segments + structural heading segments
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

- durable `TranslationJob` persistence with book/chapter scope
- Redis FIFO queue with queued-ID deduplication
- independent Docker `worker` service
- queued/stale-running job recovery
- idempotency keys
- retry policy and optional stop-on-error
- cancellation flag
- progress counters and current segment tracking
- batch translation for a chapter or whole book
- synthetic chapter/section heading segments so headings participate in the same audited translation pipeline
- `TranslationQAResult` persistence
- multi-model QA evaluators
- explicit six-dimension scoring
- weighted aggregate quality score from 0 to 100
- QA issues/verdict persistence
- QA score propagation to final TranslationVersion and Translation Memory
- translated DOCX export
- translated paragraph/list/code/caption/heading reconstruction
- translated table reconstruction when the model preserves the source row/tab grid
- source fallback when a block has no approved translation or table grid cannot be safely reconstructed
- PostgreSQL + Redis end-to-end CI integration test

## QA score

Each evaluator returns six scores from 0 to 100. BookTranslate AI computes the evaluator score deterministically:

```text
Semantic accuracy       30%
Terminology             20%
Completeness            15%
Fluency                 15%
Technical integrity     10%
Style                   10%
```

Multiple evaluator-model scores are then combined using their configured evaluator weights. The aggregate score is stored on the final `TranslationVersion` and propagated to its Translation Memory entry.

Verdicts:

```text
90–100  excellent
80–89   good
70–79   acceptable
60–69   needs_review
<60     poor
```

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

Services include frontend, FastAPI backend, PostgreSQL, Redis and the translation worker. The backend applies `alembic upgrade head` before becoming healthy; the worker starts only after backend readiness.

Useful endpoints:

- Frontend: `http://localhost:3000`
- Swagger: `http://localhost:8000/docs`
- Readiness: `http://localhost:8000/health`
- Liveness: `http://localhost:8000/liveness`

## Document API

```text
POST /api/books
GET  /api/books
GET  /api/books/{book_id}
POST /api/books/upload
GET  /api/books/{book_id}/export/docx
GET  /api/books/{book_id}/export/translated.docx
```

Supported source formats: `.docx`, `.epub`.

## Glossary API

```text
POST /api/books/{book_id}/glossary
GET  /api/books/{book_id}/glossary
```

## Segment Translation API

```text
POST /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translation-context
POST /api/segments/{segment_id}/translate
POST /api/segments/{segment_id}/translate/pipeline
POST /api/translations/{translation_id}/versions/{version_id}/finalize
GET  /api/ai/providers
```

## Translation Jobs API

```text
POST /api/books/{book_id}/translation-jobs
POST /api/chapters/{chapter_id}/translation-jobs
GET  /api/translation-jobs/{job_id}
GET  /api/books/{book_id}/translation-jobs
POST /api/translation-jobs/{job_id}/cancel
```

Conceptual whole-book job:

```json
{
  "target_language": "ru",
  "stages": [
    {"provider": "kimi", "model": "<kimi-model>", "role": "translator"},
    {"provider": "openai", "model": "<openai-model>", "role": "reviewer"},
    {"provider": "gemini", "model": "<gemini-model>", "role": "critic"},
    {"provider": "openai", "model": "<openai-model>", "role": "finalizer"}
  ],
  "qa_evaluators": [
    {"provider": "openai", "model": "<qa-model>", "weight": 1.0},
    {"provider": "gemini", "model": "<qa-model>", "weight": 1.0}
  ],
  "max_retries": 2,
  "min_quality_score": 80,
  "idempotency_key": "book-42-ru-v1"
}
```

Provider/model names remain request/configuration data rather than hard-coded project constants.

## QA API

```text
POST /api/translations/{translation_id}/versions/{version_id}/qa
GET  /api/translations/{translation_id}/versions/{version_id}/qa
```

QA can therefore be rerun independently from the batch worker with another evaluator set.

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions:

- starts PostgreSQL
- starts Redis
- applies the full Alembic migration chain through Stage 4
- enables database integration tests
- verifies Document Engine round trip
- verifies Translation Engine versioning and memory
- verifies Redis job enqueue/dedup/dequeue
- verifies whole-job processing with a fake provider
- verifies multi-model QA persistence/aggregation
- verifies translated normalized reconstruction
- validates provider adapters without live keys
- builds the Next.js frontend

No live LLM calls are made by CI.

## Current boundaries

- DOCX reconstruction is structural rather than pixel-identical.
- Formulas, footnotes/endnotes, complex hyperlinks and advanced style fidelity still need dedicated structural models.
- Translated tables are reconstructed only when the translated output preserves the original row/tab grid; otherwise the original table is retained rather than risking structural corruption.
- Figures are preserved; image text/alt-text translation is not yet a dedicated OCR/vision workflow.
- Current workers use a PostgreSQL-persisted job state plus Redis queue signal. This is appropriate for the MVP, but high-scale deployments may later add stronger leasing, provider rate-limit scheduling and distributed worker coordination.

## Next engineering stage

1. human review/approval workflow and manual version editing;
2. book-level QA dashboard and chapter consistency scoring;
3. terminology consistency checks across the whole book;
4. cost/token budgets and provider routing policies;
5. rate-limit aware scheduling/concurrency controls;
6. translated EPUB export;
7. formula/footnote/hyperlink fidelity improvements.
