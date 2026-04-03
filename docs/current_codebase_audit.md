# NarrativeSignal / AI Narrative Platform — Codebase Audit

**Scope:** Read-only inventory as of repository state at audit time. Claims cite concrete files.  
**Out of scope:** No refactors; no features not evidenced in code.

---

## 1. Product / features inventory

| Area | Status | Evidence / notes |
|------|--------|------------------|
| **Auth: register / login / refresh / me** | **Implemented** | `backend/app/api/routes/auth.py` — register (MeResponse), login (access token + httpOnly refresh cookie `narrative_refresh`), refresh, logout, `/me`, profile PATCH, change-password; JWT + `token_version` single-session in `backend/app/api/deps.py`. |
| **User / account / session** | **Implemented** | Credits, `paid_access`, `is_admin` on User; `user_is_admin` with optional env allowlist (`admin_usernames`, `admin_emails`) in `backend/app/core/config.py` + `deps.py`. |
| **Admin panel** | **Partial** | Backend: `GET/PATCH /api/admin/users`, `GET /api/admin/diag/core-data`, `POST /api/admin/market/refresh-cache` — `backend/app/api/routes/admin_routes.py` + `require_admin`. Frontend: `frontend/src/app/admin/users/page.tsx` (guards on `user.is_admin`); no broader admin UI beyond users. |
| **Dashboard structure** | **Implemented** | `frontend/src/app/dashboard/page.tsx` + `DashboardClient.tsx` — tabs `macro` \| `entity` via query `?tab=`, keyword groups, indices series, group asset, OHLCV, entity-config for charts. |
| **Macro data tab** | **Implemented** | `MacroLayout` + `api.macroNews`, `api.macroEvents`, `api.marketIndices`, macro categories API — news is **DB snapshot–backed** on GET (`backend/app/api/routes/macro.py`); worker fills snapshots. |
| **Entity data tab** | **Implemented** | `EntityDataLayout` + entity routes under portfolios — portfolios, entities, instruments, charts, news, metrics (see §2). |
| **Research / workspace** | **Implemented (data model + API)** | `backend/app/api/routes/research.py` — folders, projects, setup snapshots CRUD; `frontend/src/lib/api.ts` research\* methods; `frontend/src/app/research/page.tsx` wiring **assumed present** (page exists). |
| **Reports** | **Implemented (list/delete/count)** | `backend/app/api/routes/reports.py`; Celery `generate_daily_reports` in `backend/app/worker/celery_app.py`; reports produced in `backend/app/worker/tasks.py`. |
| **Schedules** | **Implemented** | `backend/app/api/routes/schedules.py`; Celery `tick_schedules` + `trigger_monitoring_run`; limits in `backend/app/core/limits.py`. Premium schedule types (`ai_alert`, `ai_report`, `general_alert`) **only if `user_is_admin`** — non-admins are **silently coerced** to `standard_monitor` (same file). |
| **Keyword groups** | **Implemented** | `backend/app/api/routes/keyword_groups.py` + subscriptions; dashboard + `frontend/src/lib/api.ts` `listGroups` / CRUD. |
| **Symbol / instrument search & binding** | **Implemented** | `GET /api/instruments/search` + `GET /api/market/search` + Twelve upsert paths — `backend/app/api/routes/portfolios.py`, `market.py`; frontend `api.searchInstruments`, `api.marketSearchAsInstruments`; `instrument_resolve` on entity create/update in `api.ts`. |
| **Price / time series / charts** | **Implemented** | Twelve-primary with Stooq/Yahoo fallback — `backend/app/services/market_snapshots.py`, `market/service.py` (yfinance); routes `market.py` (quote, ohlcv, ohlcv-batch, time_series, indices); Redis/DB snapshots; worker warm pools in `celery_app.py`. |
| **News ingestion / panels / filtering** | **Partial** | **Macro:** Google News RSS → Celery → DB snapshots — `backend/app/services/macro_news.py` (feedparser), `macro.py` GET reads snapshots only. **Entity:** live Google News RSS per request (cached) — `portfolios.py` `get_entity_news` → `fetch_entity_news`. **Normalizednews:** `GET .../news-documents` DB-only. Frontend: `NewsList`, entity news panel. |
| **Sentiment / momentum / acceleration (entity)** | **Partial / unclear without runtime** | Index points expose momentum etc. — `backend/app/api/routes/indices.py` + `narrative_metrics`; entity endpoints for sentiment-series, quadrant, trending, metric-series — `portfolios.py`. Quality depends on document/ingestion pipeline and daily metrics (see Celery `sync_entity_daily_metrics`). |
| **Google / search / trends** | **Implemented (Trends via pytrends)** | `backend/app/services/trends_service.py` (TrendReq, optional `trends_proxy_url`); `entity_metrics_pipeline.py` — sync search trend to `EntityDailyMetric`; config `TRENDS_*` in `.env.example`. |
| **Quadrant / 3D chart / overlay / split chart** | **Partial** | Backend: `GET .../quadrant`, `quadrant-history`, `charts/3d-data`, `metric-series/{metric}` — `portfolios.py`; 3D data service `backend/app/services/entity_chart_3d.py`. **UI sophistication** not fully audited; layout stored in `chart_layout` on entities. Some timeline/window modes remain **placeholder** — `entity_event_timeline.py` (`data_mode="placeholder"` paths, `ai_summary_placeholder`). |
| **Caching** | **Implemented** | Redis response cache middleware — `backend/app/middleware/response_cache.py` (TTLs per path; bypass for auth, market, portfolios, research, schedules, etc.); macro news Redis “last good”; Twelve/Yahoo pacing — `twelve_data_service`, `yahoo_guard.py`. |
| **Celery workers / beat** | **Implemented** | `docker-compose.yml` — `worker` + `beat`; `backend/app/worker/celery_app.py` full beat schedule (schedules tick, daily reports, macro news, macro news list snapshots, quote/OHLCV refreshes, warm pools, entity metrics, retention). |
| **Postgres models** | **Implemented** | `backend/app/models/__init__.py` lists User, portfolios, keyword groups, research, monitoring, reports, macro, news snapshots, subscriptions, community, etc. |
| **Redis** | **Implemented** | Broker/backend for Celery (`settings.redis_url`); rate limits; response cache; Yahoo guard; macro last-good cache (services). |
| **Docker / deploy / env** | **Implemented** | `docker-compose.yml` — postgres, redis, backend, worker, beat, frontend (named `frontend_next` volume); `backend/.env.example`; compose injects `DATABASE_URL` / `REDIS_URL` / optional `TWELVE_API_KEY`. |
| **Rate limiting** | **Implemented** | `backend/app/middleware/rate_limit.py` + `backend/app/core/rate_limit.py` — IP/user buckets, stricter macro/entities paths, dedicated auth paths. |
| **Auth protection** | **Implemented (JWT on protected routes)** | Most `/api/*` routers use `Depends(get_current_user)` or stricter; public: auth register/login/refresh, `GET /healthz`. |
| **Admin protection** | **Implemented for `/api/admin/*`** | `require_admin` on admin routes; frontend admin page checks `is_admin` before calling `listUsers`. |

---

## 2. Backend audit

### 2.1 Routers / mount

Central registration: `backend/app/api/router.py` — prefixes: `/api/auth`, `/api/admin`, `/api/assets`, `/api/macro`, `/api/research`, `/api/keyword-groups`, `/api/portfolios` (no extra prefix — entities under `/api/entities`), `/api/ai`, `/api/groups`, `/api/indices`, `/api/market`, `/api/reports`, `/api/schedules`, `/api/alerts`, `/api/community`.

App: `backend/app/main.py` — CORS from `CORS_ALLOW_ORIGINS` (comma-separated; empty = no browser origins), middleware order (CORS → rate limit → response cache), `init_db`, seeds admin + instruments, core data warmup thread.

### 2.2 Notable route groups

| Router | Role |
|--------|------|
| `auth.py` | Register, login, refresh, logout, me, profile, password |
| `admin_routes.py` | Users list/patch, diagnostics, enqueue market cache refresh |
| `macro.py` | Events, **news (snapshot)**, macro categories CRUD |
| `market.py` | Quote, OHLCV, batch OHLCV, time series, search, indices |
| `portfolios.py` | Portfolios CRUD, entities CRUD/terms, related instruments, comparison/search-volume/coverage/sentiment series, quadrant(+history), trending, 3D data, metric series, **entity news (live RSS)**, news-documents, price timeline + **AI summary placeholder**, instruments search |
| `research.py` | Folders, projects, setup snapshots |
| `keyword_groups.py` | Keyword group CRUD |
| `groups.py` | RSS feeds, articles, group asset, entity-config |
| `indices.py` | Keyword group time series (`/api/indices/series/{group_id}`) |
| `schedules.py` | Monitoring schedules + premium type gating |
| `reports.py` | List/delete/count reports |
| `alerts.py` | List triggered alerts |
| `ai_routes.py` | `POST /api/ai/keyword-suggestions` (Gemini, requires key) |
| `community.py` | Submissions + data requests + **placeholder email** |
| `assets.py` | **`GET /api/assets/search`** — static `EXAMPLE_SYMBOLS` list only |

### 2.3 Key services / clients

- **Twelve Data:** `backend/app/services/twelve_data_service.py` (httpx).
- **Market pipeline:** `market_snapshots.py`, `market/service.py` (Stooq, yfinance).
- **Macro news RSS:** `macro_news.py`, `macro_news_dedup.py`, snapshots `macro_news_snapshot.py`, Celery `fetch_macro_news` / `refresh_macro_news_list_snapshots`.
- **Trends:** `trends_service.py` (pytrends).
- **AI providers:** `services/ai/providers.py` (OpenAI Chat, Gemini REST); `services/ai/service.py` (`analyze_documents` for `DocumentAnalysis`).
- **Entity timeline / AI summary stub:** `entity_event_timeline.py` — `ai_summary_placeholder` explicitly “not connected”.
- **AI alert MVP:** `ai_alert.py` — heuristic + placeholder LLM/history.
- **Community email stub:** `community_email.py` — logs only.
- **Reporting markdown builders:** `reporting.py` (used from tasks).

### 2.4 Background tasks (Celery)

`backend/app/worker/tasks.py` (partial list from imports + `celery_app.py`): `tick_schedules`, `trigger_monitoring_run` (RSS ingest, analysis, spikes, AI doc analysis, AI alert/report pipelines per schedule type), `generate_daily_reports`, `fetch_macro_news`, `refresh_macro_news_list_snapshots`, `refresh_market_quotes`, warm pool Twelve tasks, active pool tasks, `refresh_market_ohlcv_snapshots`, `sync_entity_daily_metrics`, `retention_cleanup_v1`, admin `refresh_core_market_cache_admin`.

### 2.5 Config / env (code + `.env.example`)

Referenced in `backend/app/core/config.py` and `backend/.env.example`:

- `DATABASE_URL`, `REDIS_URL`, `ENV`
- `JWT_SECRET`, `JWT_ISSUER`, token lifetimes
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`
- `SMTP_*` (defined in Settings; **not used** by community email implementation)
- `DEFAULT_MONITORING_CRON`
- `TRENDS_PROXY_URL`, `TRENDS_DEFAULT_TIMEFRAME`, `TRENDS_REQUEST_SLEEP_SECONDS`
- `ADMIN_USERNAMES` / `ADMIN_EMAILS` (example comments in `.env.example`; fields `admin_usernames`, `admin_emails` in Settings)
- `TWELVE_API_KEY`
- `INSTRUMENT_SEARCH_MIN_LOCAL_BEFORE_EXTERNAL` (comment in .env.example)
- `YAHOO_FALLBACK_*` (comments)

Docker additionally passes `TWELVE_API_KEY` from host env into `backend` service (`docker-compose.yml`).

### 2.6 Dead code / placeholders / TODOs (non-exhaustive)

- `ai_summary_placeholder` — explicit placeholder for multi-provider timeline summaries (`entity_event_timeline.py`).
- `ai_alert.py` / `run_ai_report_pipeline` — placeholder deep analysis and mock scores.
- `community_email.py` — “coming soon”, no SMTP send.
- `assets.py` — comment: “Example symbols… can be replaced with DB or external API later”.
- `main.py` — dev bootstrap: fixed admin email/password (`admin@internal.test` / `admin`) if missing user — **production hazard** if left enabled.

---

## 3. Frontend audit

### 3.1 Pages (App Router)

Under `frontend/src/app/`: `page.tsx` (home), `login`, `dashboard`, `dashboard/entities/[id]`, `profile`, `schedules`, `reports`, `research`, `community`, `admin/users`, `groups/[id]`, `news/[id]` (macro news detail from session/cache + `macroEvents` fallback).

### 3.2 API wiring

- Single client: `frontend/src/lib/api.ts` — `fetch` to same-origin `/api/*`; **Next.js rewrites** to `BACKEND_URL` — `frontend/next.config.js`.
- Browser stores access token in `localStorage` (`narrative_access_token`); refresh via cookie — see `request()` retry on 401.

### 3.3 Mock / placeholder / limited UI

- **`/api/assets/search`** — hardcoded example list (`assets.py`); frontend `api.assetsSearch` uses it — **not** real market search (contrast `searchInstruments` / `marketSearchAsInstruments`).
- **AI timeline summary** — UI can call API but backend returns `status: "placeholder"` text (`ai_summary_placeholder`).
- **Premium schedules** — non-admin users selecting AI alert/report types get `standard_monitor` on server without error — behavior gap if UI exposes those types.
- **Community “email admin”** — no real notification.

### 3.4 Controls that may feel incomplete

- Anything backed by **Celery** (macro news snapshots, normalized news, some metrics) needs worker/beat running or data stays stale/empty with “warming” states.
- **Gemini keyword suggestions** return 503 if `GEMINI_API_KEY` unset (`ai_routes.py`).
- **Document AI analysis** in monitoring runs requires `get_provider()` to resolve (OpenAI or Gemini key).

---

## 4. External provider / API audit

| Category | Provider / mechanism | Where | Depends on | Wired? | Secret / config |
|----------|----------------------|------|------------|--------|-----------------|
| Market data (primary) | **Twelve Data** API | `twelve_data_service.py`, `market.py`, `market_snapshots.py`, worker tasks | Quotes, OHLCV, symbol search, indices | **Yes** if `TWELVE_API_KEY` set | `twelve_api_key`, compose `TWELVE_API_KEY` |
| Market data (fallback) | **Stooq** HTTP | `market/service.py`, `market_snapshots.py` | Quotes/OHLCV when Twelve unavailable | **Yes** (no key in code) | None |
| Market data (fallback) | **Yahoo / yfinance** | `market/service.py`, `yahoo_guard.py` | Last-resort OHLCV/quote | **Yes** | Pacing: `YAHOO_*` settings |
| Macro / entity news (RSS) | **Google News** RSS URLs | `macro_news.py`, entity `fetch_entity_news` (via portfolios route docstring) | Macro snapshots, entity news panel | **Yes** (HTTP RSS; no API key) | None; reliability/rate limits external |
| Search trends | **Google Trends (pytrends)** | `trends_service.py`, `entity_metrics_pipeline.py` | Search trend series, 3D chart search axis | **Partial** — works when pytrends/Google allows; optional `TRENDS_PROXY_URL` | Proxy + sleep settings |
| LLM | **Google Gemini** | `ai_routes.py`, `ai/providers.py` | Keyword suggestions; optional doc analysis provider | **Partial** — keyword suggestions **require** key; 503 otherwise | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| LLM | **OpenAI** | `ai/providers.py`, `analyze_documents` | Document analysis when OpenAI selected first | **Partial** — needs `OPENAI_API_KEY` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| LLM | **Anthropic / Qwen** | Labels only in `ai_summary_placeholder` | Timeline AI summary UI allows provider enum | **Not wired** — placeholder text only | Implied future keys (not in Settings) |
| Email | **SMTP** (planned) | `core/config` has `smtp_*`; `community_email.py` not implemented | Community forwards | **Not wired** | `SMTP_*` unused for sends |
| Infra | **PostgreSQL** | SQLAlchemy | All persistent data | **Yes** | `DATABASE_URL` |
| Infra | **Redis** | Celery, rate limit, response cache, guards | Jobs + caching + limits | **Yes** | `REDIS_URL` |

---

## 5. Security / config audit

| Topic | Finding |
|-------|---------|
| **API keys on frontend** | `frontend/.env.example` only exposes `BACKEND_URL`. `NEXT_PUBLIC_SITE_URL` in `page.tsx` is non-secret site URL. **No provider keys** in audited frontend env template. Rewrites proxy `/api` server-side — browser does not need backend secrets. |
| **Env handling** | Backend secrets via env + `.env` file (standard pydantic-settings). **Risk:** default/long-lived access token in `Settings` comment (`accessTokenExpireMinutes` 7 days default in code) — tune for production. |
| **Hardcoded credentials** | `main.py` seeds `admin` / `admin@internal.test` / password `admin` — must be removed or gated for any real deployment. |
| **Admin routes** | Protected by `require_admin` + DB flag + optional allowlist. |
| **Overly open routes** | `GET /healthz` public (expected). `/docs` availability = default FastAPI (consider disabling in prod). |
| **Rate limiting** | Present for `/api` via ASGI middleware (`rate_limit.py`). |
| **CORS** | Origins from `CORS_ALLOW_ORIGINS` (e.g. set in compose for dev browser → published frontend port). |

---

## 6. Deliverables

### A. Executive summary

- **Already works:** Full auth session model; JWT + refresh cookie; rich **portfolio/entity** REST surface; **market** quotes/OHLCV/search with Twelve + fallbacks; **macro news** via DB snapshots + Celery RSS pipeline; **keyword groups**, **RSS feeds**, **indices** series; **schedules** + **Celery beat**; **reports** storage; **research** folders/projects/snapshots; **Redis** caching + rate limits; **Docker** stack.
- **Half-done:** **AI** features (keyword suggestions need Gemini; document analysis needs keys; timeline **AI summary** is placeholder; **AI alert/report** schedules are heuristic/mock); **community email** logging only; **assets search** static list; **Google Trends** depends on pytrends reliability; **normalized entity news** depends on ingestion jobs/populated DB.
- **Missing / not wired:** Real **SMTP** (or other) notifications; **Anthropic/Qwen** providers for timeline summaries; production-hardening (remove seed admin, CORS, docs); possible **admin UI** beyond user list.

### B. Feature matrix

| Feature | Status | Backend route / service | Frontend | External provider? | Notes |
|---------|--------|-------------------------|----------|-------------------|--------|
| Register / login / refresh | Implemented | `/api/auth/*` | `login/page`, `api.ts` | No | Refresh cookie + Bearer access |
| Me / profile | Implemented | `/api/auth/me`, profile | `profile/page`, `UserContext` | No | |
| Admin users | Implemented | `/api/admin/users` | `admin/users/page.tsx` | No | Also diag + market cache enqueue |
| Dashboard macro tab | Implemented | `/api/macro/news`, events, `/api/market/indices` | `MacroLayout`, `DashboardClient` | Google News RSS (worker), Twelve for indices | News GET = snapshot |
| Dashboard entity tab | Implemented | `/api/keyword-groups`, `/api/indices/series`, `/api/market/*`, `/api/groups/*` | `EntityDataLayout` | Twelve, Yahoo, Stooq | |
| Entity detail | Implemented | `/api/entities/*`, portfolios | `EntityDetailPageClient` | Twelve + trends + RSS | Many sub-features |
| Entity news (live) | Implemented | `GET .../entities/{id}/news` | News panels | Google News RSS | Cached ~10m (route docstring) |
| Macro news list | Implemented | `GET /api/macro/news` | `NewsList` | Worker: Google News RSS | DB snapshot read path |
| Market charts | Implemented | `/api/market/ohlcv`, `quote`, `time_series` | Charts in dashboard/entity | Twelve, fallbacks | |
| Instrument search | Implemented | `/api/instruments/search`, `/api/market/search` | Entity forms | Twelve when configured | |
| Keyword groups | Implemented | `/api/keyword-groups` | Dashboard | No | |
| RSS feeds / articles | Implemented | `/api/groups/{id}/feeds`, `articles` | `groups/[id]` | RSS sources | Ingest in monitoring/tasks |
| Research workspace | Implemented | `/api/research/*` | `research/page.tsx` | No | Layout JSON in DB |
| Schedules | Implemented | `/api/schedules`, worker | `schedules/page.tsx` | No | Premium types admin-only |
| Reports | Implemented | `/api/reports`, tasks | `reports/page.tsx` | No | Markdown bodies |
| Alerts | Implemented (list) | `/api/alerts` | Schedules/report flows | Partial LLM | Generation via tasks |
| AI keyword suggestions | Partial | `POST /api/ai/keyword-suggestions` | If used in UI | **Gemini** | 503 without key |
| AI timeline summary | Placeholder | `POST .../price-timeline/ai-summary` | Timeline UI | Future LLM | Returns placeholder text |
| AI alert / report pipeline | Partial | `ai_alert.py`, tasks | Schedules | Heuristic + mock | Not full LLM |
| Community | Partial | `/api/community/*` | `community/page.tsx` | Email N/A | DB persist; no email send |
| Static asset search | Placeholder | `GET /api/assets/search` | `api.assetsSearch` | None | Replace with real search |
| Google Trends metrics | Partial | trends service, entity metrics | Entity charts | pytrends | Proxy optional |
| Community email | Missing | `community_email.py` | — | SMTP etc. | Log-only |

### C. API / provider priority matrix

| Provider category | Specific | Used now or later | Feature | Env / config | Priority |
|-------------------|----------|-------------------|---------|--------------|----------|
| Market | Twelve Data | Now | Quotes, OHLCV, search | `TWELVE_API_KEY` | **P0** for production quality |
| Market | Stooq / Yahoo | Now (fallback) | Same | Yahoo pacing settings | P1 (reliability) |
| News | Google News RSS | Now | Macro + entity news | None | P0 ops (worker + network) |
| Trends | pytrends | Now | Search trend / 3D | `TRENDS_PROXY_URL`, sleep | P1 |
| LLM | Gemini | Now (optional) | Keywords; doc analysis | `GEMINI_API_KEY` | P1 |
| LLM | OpenAI | Now (optional) | Doc analysis | `OPENAI_API_KEY` | P1 |
| LLM | Anthropic / Qwen | Later | Timeline AI enum only | Not in Settings | P2 |
| Email | SMTP (planned) | Later | Community forwards | `SMTP_*` unused | P2 |
| DB / Redis | Postgres / Redis | Now | All | `DATABASE_URL`, `REDIS_URL` | P0 |

### D. What to wire next (top 5, practical order)

1. **Operational:** Run **worker + beat** in all environments where macro news, metrics, and schedules matter; confirm `TWELVE_API_KEY` and Redis connectivity.
2. **Twelve Data:** Ensure key + symbol mapping coverage for your entity universe (credits/warm pools already conservative in `celery_app.py`).
3. **LLM for product value:** Wire **`POST .../price-timeline/ai-summary`** to `OpenAIProvider`/`GeminiProvider` (or add Anthropic) instead of `ai_summary_placeholder` — reuse `services/ai/providers.py`.
4. **AI schedules:** Replace mocks in `ai_alert.py` with real document/news inputs + same provider abstraction; expose premium schedule types intentionally to paid users (not only admin) if product requires it.
5. **Community / ops:** Implement `forward_submission_email` / `forward_data_request_email` with SMTP or transactional provider — config fields already partially exist on `Settings`.

### E. What not to touch yet

- Broad **refactors** of `portfolios.py` (large surface; high regression risk) until provider wiring is stable.
- **New chart types / split views** before core **market + trends + news** data paths are reliable for your symbols.
- **Anthropic/Qwen** UI promises until backend Settings + provider classes exist (currently placeholder strings only).
- Removing **Yahoo/Stooq** fallback before Twelve coverage is proven — code explicitly depends on fallback for resilience (`market_snapshots.py`).

---

*End of audit. Regenerate after major merges or provider additions.*
