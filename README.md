# BookTranslate AI

AI-powered platform for technical book translation with multi-model QA.

## Stage 1

Current repository skeleton:

- Next.js + TypeScript frontend
- FastAPI backend
- PostgreSQL database
- Redis cache/queue foundation
- Docker Compose for local/cloud development
- Backend health checks for PostgreSQL and Redis

## Project structure

```text
BookTranslate-AI/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── main.py
│   │   └── redis_client.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── Dockerfile
│   ├── next-env.d.ts
│   ├── package.json
│   └── tsconfig.json
├── .env.example
├── .gitignore
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

3. Open:

- Frontend: http://localhost:3000
- FastAPI Swagger: http://localhost:8000/docs
- Backend health: http://localhost:8000/health

Expected health response when all dependencies are available:

```json
{
  "status": "ok",
  "database": true,
  "redis": true
}
```

## Stop

```bash
docker compose down
```

To also remove local database/cache volumes:

```bash
docker compose down -v
```

## Definition of Done — Stage 1

Stage 1 is complete when:

- `docker compose up --build` starts all four services;
- Next.js is reachable on port 3000;
- FastAPI is reachable on port 8000;
- `/docs` opens Swagger UI;
- `/health` reports PostgreSQL and Redis as available;
- PostgreSQL data persists in a Docker volume;
- Redis starts and responds to `PING`.

## Next stage

Stage 2 will add book upload, document parsing, persistent project entities, chapters and segments. AI model integration is intentionally deferred until the document workflow is stable.
