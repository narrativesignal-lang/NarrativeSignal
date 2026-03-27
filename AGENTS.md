# Agent notes (this repo)

## Next.js: `Cannot find module './819.js'` (or similar)

Cause: corrupted or **out-of-sync `frontend/.next`** (especially with `docker-compose` bind-mounting `./frontend`).

### Built-in behavior (`frontend/package.json`)

- **`npm run clean`** — best-effort removal of `.next/cache`, `.next/server`, `.next/static`, then full `.next`; **never fails** (EBUSY/locked → skip and log; `next dev` still runs).
- **`npm run dev`** — `clean` then `next dev`.
- **`npm run build`** — **`prebuild`** runs **`npm run clean`** then `next build`.
- **`npm run dev:docker`** — same as **`npm run dev`** (alias for compose/scripts).

Docker Compose `frontend` uses `npm install && npm run dev`, and mounts a **named volume** `frontend_next:/app/.next` so the **host’s `./frontend/.next` is not used inside the container** (avoids missing chunk `819.js` when host and container builds diverge).

### Minimum commands (after pulling code)

**Local dev**

```bash
cd frontend && npm install && npm run dev
```

**Docker (recommended after any frontend dependency or Next structural change)**

```bash
docker compose down
docker compose up --build frontend
```

**Standard “restart frontend” (pick one)**

- Docker: `docker compose restart frontend` (uses existing images/volumes).
- Full rebuild when things feel cursed: `docker compose up --build frontend`.

### If it still breaks

```bash
cd frontend && npm run clean && npm run dev
```

Or remove the named volume and rebuild: `docker compose down`, `docker volume rm <project>_frontend_next` (name from `docker volume ls`), then `docker compose up --build`.

### When editing frontend in this repo

Use **`cd frontend && npm run build`** to verify; **clean runs automatically** via `prebuild`.
