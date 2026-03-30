# Admin-only AI gating (temporary)

## 1. Features treated as AI / token-costing

These paths may invoke **OpenAI**, **Google Gemini**, or future paid LLM APIs, or are reserved for **AI monitoring pipelines**:

| Feature | Backend |
|--------|---------|
| Keyword suggestions | `POST /api/ai/keyword-suggestions` → `api/routes/ai_routes.py` |
| Entity price-timeline AI summary | `POST /api/entities/{id}/price-timeline/ai-summary` → `api/routes/portfolios.py` |
| Document AI analysis | `app.services.ai.service.analyze_documents` (OpenAI/Gemini via `get_provider`) |
| AI alert / AI report / general alert schedules | Types `ai_alert`, `ai_report`, `general_alert` → `worker/tasks.py`, `services/ai_alert.py` |

**Explicitly not treated as paid-AI** (heuristic / no LLM in current code):

- `analyze_documents_for_group` in `services/analysis.py` (keyword match + word-list sentiment)
- Macro/news RSS, market data (Twelve/Yahoo/Stooq), Google Trends (pytrends) — separate product/API costs, not gated by this rule unless you extend `can_use_paid_ai` later.

## 2. How gating works

Tier keys and the feature map live in **`app/core/feature_access.py`**; account plan labels live in **`app/core/plan_entitlements.py`** (`PlanCode`, `AiAccessLevel`). Credit stubs live in **`app/core/feature_billing_hooks.py`** (not wired into routes). See **`docs/feature_access_and_tiers.md`** and **`docs/ai_usage_ledger.md`**.

### Constants (`app/core/ai_access.py`)

| Name | Use |
|------|-----|
| `AI_FEATURES_FORBIDDEN_DETAIL` | HTTP **403** `detail` for direct AI actions forbidden to the user. |
| `AI_BACKGROUND_SKIP_DETAIL` | Celery `MonitoringRun.detail` when an AI schedule is skipped (`"Skipped: " +` same sentence). |
| `AI_RUN_SKIP_REASON_CODE` | Stable string `"ai_requires_admin"` in worker/pipeline return dicts (`reason` key). |
| `AI_SCHEDULE_TYPES` | `frozenset({"ai_alert", "ai_report", "general_alert"})` — must stay a subset of `monitoring.SCHEDULE_TYPES`. |

### Enforcement points

- **Central rule:** `can_access_feature(user, feature_key)` — admins always allowed; non-admins allowed for `FREE` tier only; **LIGHT_AI** / **HEAVY_AI** denied today via `_non_admin_ai_entitled` (see `feature_access.py`).
- **HTTP:** `require_feature(FeatureKey.…)` on keyword-suggestions (`KEYWORD_SUGGESTIONS`) and price-timeline AI summary (`TIMELINE_AI_SUMMARY`) → **403** + `AI_FEATURES_FORBIDDEN_DETAIL`. Optional alias `require_paid_ai_access` = heavy document feature only (legacy name).
- **Schedules (create):** `schedules.py` — if AI schedule type, `can_access_feature(user, feature_key_for_schedule_type(...))` → same 403 when denied.
- **Celery `trigger_monitoring_run`:** same feature key per schedule type; skip path unchanged (`AI_BACKGROUND_SKIP_DETAIL`, `AI_RUN_SKIP_REASON_CODE`).
- **`analyze_documents`:** `FeatureKey.DOCUMENT_LLM_ANALYSIS` before `get_provider()`.
- **`run_ai_alert_pipeline` / `run_ai_report_pipeline`:** `SCHEDULE_AI_ALERT`, `SCHEDULE_AI_REPORT`, or `SCHEDULE_GENERAL_ALERT` as appropriate.

**Compatibility:** `can_use_paid_ai(user)` remains and equals heavy document-tier access (same outcome as today for all previous call sites that used it for “any HEAVY bundle”).

### Frontend

- **Schedules:** AI `<option>`s only after `!userLoading && isAdmin`; if the user turns non-admin after load, effect resets `schedule_type` off AI types only after `userLoading` is false.
- **Entity create/detail:** AI suggestion control hidden while `userLoading`; then admin button vs “Admin only for now” label.
- **Timeline panel:** AI summary controls only when `access.is_admin` from the points API; others see `timeline.aiAdminOnlyNote`.

## 3. Who can access AI now

- **Admin accounts** (`is: true`, subject to optional `ADMIN_USERNAMES` / `ADMIN_EMAILS` narrowing — see `app/core/user_admin.py`).
- **All other users:** no AI endpoints above; monitoring runs do not call `analyze_documents` for them; AI schedule execution is skipped.

## 4. Replacing this with real paid tiers

1. Implement entitlement in **`_non_admin_ai_entitled`** in `app/core/feature_access.py` (plan_code, ai_access_level, credits_balance, tier).
2. Keep all routes and workers calling **`can_access_feature`** / **`require_feature`** so rules stay in one place.
3. Optionally re-enable **credit debiting** for non-admin AI where product-appropriate.
4. Update **`docs/feature_access_and_tiers.md`**, this file, and in-app copy when the product rule changes.

## Testing

- **Unit tests** (no full Docker stack):  
  `cd backend && pip install -r requirements.txt && python -m pytest tests/test_ai_access_gating.py tests/test_feature_access.py`
- Covers: `can_use_paid_ai`, `can_access_feature` / tiers, shared constants, `AI_SCHEDULE_TYPES ⊆ SCHEDULE_TYPES`, `analyze_documents` acting-user guard + mocked provider for admin, AI pipeline early-exit for non-admin with `AI_RUN_SKIP_REASON_CODE`, stable 403 message string.

## `user_is_admin` location

- Implemented in **`app/core/user_admin.py`** and re-exported from **`app/api/deps.py`** for route dependencies. This avoids import cycles with the DB session module when `can_use_paid_ai` runs from workers or services.
