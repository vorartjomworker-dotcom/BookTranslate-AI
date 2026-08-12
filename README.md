# BookTranslate AI

AI-powered platform for structured technical-book translation with persistent document reconstruction, translation memory and provider-neutral AI orchestration.

## Current status

### Stage 1 — Infrastructure ✅

- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL
- Redis foundation
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

### Stage 3 — Translation Engine V1

Translation model:

```text
Segment
└── Translation (per target language)
    ├── TranslationVersion 1 — translator
    ├── TranslationVersion 2 — reviewer
    ├── TranslationVersion 3 — critic/finalizer
    └── selected final version

ModelRun -> provider/model/prompt/tokens/latency/output/error
PromptVersion -> versioned system prompt + template
Book -> GlossaryTerm
Book -> TranslationMemoryEntry
```

Implemented on the translation-engine branch:

- persistent `Translation` and immutable-style `TranslationVersion` history
- `ModelRun` audit trail for model/provider calls
- versioned `PromptVersion`
- per-book glossary/terminology
- exact-hash Translation Memory with approved final translations
- Context Builder with neighbouring source segments, glossary and Translation Memory
- provider-neutral `ModelGateway`
- OpenAI adapter using the Responses API
- Kimi adapter using OpenAI-compatible chat completions
- Gemini adapter using the Interactions API
- AITUNNEL adapter using OpenAI-compatible chat completions
- configurable translator/reviewer/critic/finalizer pipeline
- finalization updates the compatibility `Segment.translated_text` field and writes the approved result into Translation Memory
- provider HTTP tests with mocked transports: no real API keys are required in CI
- PostgreSQL integration test for translation versioning, model runs, finalization and Translation Memory

## Project structure

```text
BookTranslate-AI/
├── backend/
│   ├── alembic/versions/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── gateway.py
│   │   │   ├── schemas.py
│   │   │   └── providers/
│   │   │       ├── openai.py
│   │   │       ├── kimi.py
│   │   │       ├── gemini.py
│   │   │       └── aitunnel.py
│   │   ├── api/
│   │   │   ├── books.py
│   │   │   ├── upload.py
│   │   │   ├── export.py
│   │   │   ├── glossary.py
│   │   │   ├── translations.py
│   │   │   └── ai.py
│   │   ├── models/
│   │   └── services/
│   │       ├── context_builder.py
│   │       ├── prompt_builder.py
│   │       ├── translation_engine.py
│   │       └── translation_memory.py
│   └── tests/
├── frontend/
├── .github/workflows/ci.yml
├── .env.example
└── docker-compose.yml
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

Add only the provider keys you intend to use. Empty providers remain disabled:

```env
OPENAI_API_KEY=
KIMI_API_KEY=
GEMINI_API_KEY=
AITUNNEL_API_KEY=
```

Never commit real API keys. Docker Compose forwards the configured variables into the backend container.

Start the stack:

```bash
docker compose up --build
```

Docker Compose applies `alembic upgrade head` before starting FastAPI.

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
```

Supported source formats:

- `.docx`
- `.epub`

## Glossary API

```text
POST /api/books/{book_id}/glossary
GET  /api/books/{book_id}/glossary
```

Glossary matches are automatically injected into translation context for the current segment.

## Translation API

```text
POST /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translations
GET  /api/segments/{segment_id}/translation-context
POST /api/segments/{segment_id}/translate
POST /api/segments/{segment_id}/translate/pipeline
POST /api/translations/{translation_id}/versions/{version_id}/finalize
GET  /api/ai/providers
```

`GET /api/ai/providers` exposes provider names only; it never returns API keys.

Example conceptual pipeline request:

```json
{
  "target_language": "ru",
  "stages": [
    {"provider": "kimi", "model": "<configured-kimi-model>", "role": "translator"},
    {"provider": "openai", "model": "<configured-openai-model>", "role": "reviewer"},
    {"provider": "gemini", "model": "<configured-gemini-model>", "role": "critic"},
    {"provider": "openai", "model": "<configured-openai-model>", "role": "finalizer"}
  ],
  "finalize_last": true
}
```

Model names are intentionally configuration/request data rather than hard-coded project constants.

## Translation lifecycle

```text
Source Segment
    ↓
Context Builder
    ├── neighbouring segments
    ├── Glossary
    └── Translation Memory
    ↓
Model Gateway
    ↓
Translator
    ↓
Reviewer
    ↓
Critic / Finalizer
    ↓
TranslationVersion history
    ↓
Approved final version
    ├── Segment.translated_text compatibility field
    └── Translation Memory
```

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions:

- starts PostgreSQL
- applies the complete Alembic migration chain
- enables `RUN_DB_INTEGRATION=1`
- runs Document Engine database round-trip tests
- runs Translation Engine database round-trip tests
- validates provider request/response adapters with `httpx.MockTransport`
- builds the Next.js frontend

No live LLM calls are made by CI.

## Current boundaries

Document Reconstruction V1 is structural rather than pixel-identical. Formula, footnote/endnote, complex hyperlink and advanced table-style fidelity still need dedicated document models.

Translation Engine V1 currently executes requested model calls in the HTTP request lifecycle. Before large-book production processing, model orchestration should move to durable background jobs/workers using the existing Redis foundation, with retries, idempotency, rate limiting and job progress reporting.

## Next stage

After Translation Engine V1 is stable:

1. durable translation jobs/workers;
2. translated-document reconstruction using selected `TranslationVersion` values;
3. QA result model and explicit multi-model quality scoring;
4. terminology consistency checks across chapters;
5. batch/chapter/book translation orchestration;
6. human approval/review workflow;
7. cost/token telemetry and provider routing policies.
