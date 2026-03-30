# Agent notes (this repo)

## Next.js: `Cannot find module './819.js'` (or similar)

Cause: corrupted or **out-of-sync `frontend/.next`** (especially with `docker-compose` bind-mounting `./frontend`).

### Built-in behavior (`frontend/Dockerfile` + `package.json`)

- **Package manager:** **pnpm 9.15.x** (Corepack in Node 20). Lockfile: **`pnpm-lock.yaml`**.
- **`pnpm run clean`** — best-effort removal of `.next/cache`, `.next/server`, `.next/static`, then full `.next`; **never fails** (EBUSY/locked → skip and log; `next dev` still runs).
- **`pnpm run dev`** — `clean` then `next dev`.
- **`pnpm run build`** — **`prebuild`** runs **`pnpm run clean`** then `next build`.
- **`pnpm run dev:docker`** — same as **`pnpm run dev`** (alias for compose/scripts).

Docker Compose `frontend` uses **`pnpm install --frozen-lockfile && pnpm run dev`**, and mounts a **named volume** `frontend_next:/app/.next` so the **host’s `./frontend/.next` is not used inside the container** (avoids missing chunk `819.js` when host and container builds diverge).

### Minimum commands (after pulling code)

**Local dev**

```bash
cd frontend && corepack enable && corepack prepare pnpm@9.15.5 --activate && pnpm install && pnpm run dev
```

(On environments where Corepack cannot be enabled system-wide, use `npx pnpm@9.15.5 install` / `npx pnpm@9.15.5 run dev`.)

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
cd frontend && pnpm run clean && pnpm run dev
```

Or remove the named volume and rebuild: `docker compose down`, `docker volume rm <project>_frontend_next` (name from `docker volume ls`), then `docker compose up --build`.

### When editing frontend in this repo

Use **`cd frontend && pnpm run build`** to verify; **clean runs automatically** via `prebuild`.
