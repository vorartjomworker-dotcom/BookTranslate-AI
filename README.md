# BookTranslate AI

AI-powered platform for technical book translation with structured document processing and a future multi-model QA pipeline.

## Current status

### Stage 1 — Infrastructure ✅

Implemented:

- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL database
- Redis cache/queue foundation
- Docker Compose development environment
- PostgreSQL and Redis readiness checks

### Stage 2 — Document Engine V1 ✅

The persistent document model is now:

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

- async SQLAlchemy sessions and Alembic migrations
- `Book`, `Chapter`, `Section`, `Block`, `Segment`
- `Asset`, `Figure`, `DocumentTable`, `Caption`
- persistent source-file and extracted-asset storage
- EPUB and DOCX upload/parsing
- chapter and section hierarchy
- ordered document blocks
- paragraph, list-item, code and blockquote classification
- table extraction with cell structure
- image extraction and SHA-256 asset identity
- figure/caption relationships
- deterministic translation segments with source hashes
- Books API and upload API
- Reconstruction Engine V1 for DOCX
- DOCX export from persisted PostgreSQL state
- PostgreSQL migration validation in CI
- parser/reconstruction tests
- database end-to-end round-trip test
- frontend production build gate

AI model integration remains intentionally deferred until the document workflow is stable enough for translation orchestration.

## Project structure

```text
BookTranslate-AI/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/
│   │   │   ├── books.py
│   │   │   ├── upload.py
│   │   │   └── export.py
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── models/
│   │   │   ├── asset.py
│   │   │   ├── base.py
│   │   │   ├── block.py
│   │   │   ├── book.py
│   │   │   ├── caption.py
│   │   │   ├── chapter.py
│   │   │   ├── document_table.py
│   │   │   ├── figure.py
│   │   │   ├── section.py
│   │   │   └── segment.py
│   │   ├── services/
│   │   │   ├── document_export.py
│   │   │   ├── document_parser.py
│   │   │   ├── docx_parser.py
│   │   │   ├── epub_structured_parser.py
│   │   │   ├── reconstruction.py
│   │   │   └── segmentation.py
│   │   ├── db.py
│   │   ├── main.py
│   │   └── redis_client.py
│   ├── tests/
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
├── .github/workflows/ci.yml
├── .env.example
├── docker-compose.yml
└── README.md
```

## Run

1. Copy the environment template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Start the stack:

```bash
docker compose up --build
```

Docker Compose runs `alembic upgrade head` before starting the FastAPI server.

3. Open:

- Frontend: http://localhost:3000
- FastAPI Swagger: http://localhost:8000/docs
- Backend readiness: http://localhost:8000/health
- Backend liveness: http://localhost:8000/liveness

If PostgreSQL or Redis is unavailable, `/health` returns HTTP 503.

## Document API

```text
POST /api/books
GET  /api/books
GET  /api/books/{book_id}
POST /api/books/upload
GET  /api/books/{book_id}/export/docx
```

Current supported input formats:

- `.epub`
- `.docx`

The upload pipeline stores the original file and extracted assets, preserves ordered structural blocks, persists the normalized document in PostgreSQL and creates deterministic translation segments.

The DOCX export endpoint reconstructs a source-language DOCX from the persisted normalized model. It is intended as a structural-fidelity gate before translated reconstruction is introduced.

## Tests and CI

From `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions additionally starts PostgreSQL, applies `alembic upgrade head`, runs the database round-trip integration test and builds the Next.js frontend.

## Reconstruction V1 scope

Currently preserved/reconstructed:

- chapter headings
- section/subsection headings
- paragraphs
- ordered source blocks
- bullet/numbered list semantics
- code/blockquote block type
- tables and cell values
- figures/images
- captions

Known V1 limitations:

- exact typography/layout is not reproduced pixel-for-pixel
- inline image/text ordering inside the same DOCX paragraph is approximated
- formulas, footnotes/endnotes and complex hyperlinks need dedicated structural models
- advanced table merges/styles are not yet reconstructed faithfully
- EPUB export is not yet implemented

## Next stage — Translation Engine

The next engineering stage is provider-neutral translation infrastructure:

1. `Translation` and `TranslationVersion` persistence;
2. glossary/terminology model;
3. Translation Memory keyed by deterministic source hashes;
4. Context Builder for chapter/section/neighbouring-segment context;
5. Model Gateway abstraction;
6. provider adapters for Kimi, OpenAI, Gemini and optionally AI Tunnel;
7. translator/reviewer/critic orchestration;
8. multi-model QA and quality scoring;
9. translated DOCX reconstruction.

LLM provider code should not bypass the Model Gateway or write directly into source document entities.
