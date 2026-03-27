# AI Narrative & Sentiment Investing Platform

Monorepo for an AI-powered narrative monitoring SaaS.

## Stack

- **Backend**: FastAPI (Python)
- **DB**: PostgreSQL
- **Task queue**: Redis + Celery (worker + beat scheduler)
- **Frontend**: Next.js (React) + Tailwind

## Quick start (Docker)

1) Copy env files:

- `backend/.env.example` → `backend/.env`
- `frontend/.env.example` → `frontend/.env.local`

2) Start services:

```bash
docker compose up --build
```

3) Open:

- Backend API docs: `http://localhost:8000/docs`
- Frontend dashboard: `http://localhost:3000`

## Notes

- Celery Beat schedules monitoring runs; the worker executes ingestion + index calculation + AI analysis.
- This is an MVP scaffold intended to be extended (more sources, richer UI, billing, etc.).

