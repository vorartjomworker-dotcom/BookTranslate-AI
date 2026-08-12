# BookTranslate AI

AI-powered platform for technical book translation with structured document processing and a future multi-model QA pipeline.

## Current status

### Stage 1 — Infrastructure

Implemented:

- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL database
- Redis cache/queue foundation
- Docker Compose development environment
- PostgreSQL and Redis readiness checks

### Stage 2 — Document Engine foundation

Implemented in `feature/document-engine`:

- SQLAlchemy models: `Book`, `Chapter`, `Segment`
- async SQLAlchemy sessions
- Alembic migrations
- persistent upload storage
- EPUB upload and parsing
- DOCX upload and parsing
- chapter extraction
- deterministic segment generation
- SHA-256 source hashes for future Translation Memory/deduplication
- Books API
- upload API
- unit tests for segmentation, EPUB and DOCX parsing
- GitHub Actions CI for backend tests and frontend build

AI model integration is intentionally deferred until the document workflow is stable.

## Project structure

```text
BookTranslate-AI/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/
│   │   │   ├── books.py
│   │   │   └── upload.py
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── models/
│   │   │   ├── base.py
│   │   │   ├── book.py
│   │   │   ├── chapter.py
│   │   │   └── segment.py
│   │   ├── services/
│   │   │   ├── document_parser.py
│   │   │   ├── docx_parser.py
│   │   │   ├── epub_parser.py
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

Healthy readiness response:

```json
{
  "status": "ok",
  "database": true,
  "redis": true
}
```

If PostgreSQL or Redis is unavailable, `/health` returns HTTP 503.

## Document API

Create a book record:

```text
POST /api/books
```

List books:

```text
GET /api/books
```

Get one book:

```text
GET /api/books/{book_id}
```

Upload and parse a book:

```text
POST /api/books/upload
```

Current supported upload formats:

- `.epub`
- `.docx`

The upload pipeline stores the original file, extracts chapters, segments source text and persists the result in PostgreSQL.

## Tests

From `backend/`:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Stop

```bash
docker compose down
```

To also remove local database, Redis and upload volumes:

```bash
docker compose down -v
```

## Next stage

The next engineering step is to harden the Document Engine before adding AI providers:

1. preserve richer document structure (tables, figures, captions, code blocks and section hierarchy);
2. add integration tests for upload + PostgreSQL persistence;
3. add job/worker processing for large books;
4. add object-storage abstraction for source assets;
5. then introduce a provider-neutral Model Gateway for Kimi, OpenAI, Gemini and other models;
6. build Translation Memory, terminology management and multi-model QA on top of persistent segments.
