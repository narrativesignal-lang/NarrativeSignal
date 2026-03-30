# Feature access, tiers, and future billing

This document describes the **central feature access layer** introduced for future plans, subscriptions, and credits — without implementing payments.

## End-to-end path (what exists now vs later)

```text
Feature access          → Implemented: ``can_access_feature`` / ``require_feature`` (admin bypass; non-admin FREE only for AI today).
Entitlement (plan)      → Partially ready: ``PlanCode`` / ``AiAccessLevel`` on ``User``; ``_non_admin_ai_entitled`` still always denies AI for non-admins.
Usage logging           → Proposed only: ``docs/ai_usage_ledger.md`` + ``AiUsageLedgerRow`` dataclass (no DB table yet).
Credits charging        → Stub only: ``charge_feature_credits`` (no-op); ``can_consume_feature`` (always True); ``estimate_feature_credit_cost`` (returns 0).
Billing / checkout      → Not implemented (no Stripe).
```

Recommended order when you implement metering:

1. **`can_access_feature`** — tier + admin (unchanged contract).
2. **`can_consume_feature`** — balance / quota (replace stub).
3. Execute LLM / job.
4. **`charge_feature_credits`** + append **usage ledger** row (replace stubs).

## Current effective behavior (unchanged)

- **Admin users** (`user_is_admin`, including configured admin emails/usernames) may use **all** features, including every **LIGHT_AI** and **HEAVY_AI** capability.
- **Non-admin users** may use **FREE** features only. All LLM-oriented product paths remain **denied** (HTTP 403 with `AI_FEATURES_FORBIDDEN_DETAIL`, worker skip with `AI_RUN_SKIP_REASON_CODE`).

Stub hooks are **not** called from production code; they do not affect this behavior.

## Canonical plan and access labels

Defined in **`app.core.plan_entitlements`** (string enums — use ``.value`` for DB/API):

| `PlanCode`   | Stored value  |
|-------------|---------------|
| `FREE`      | `free`        |
| `BASIC_AI`  | `basic_ai`    |
| `FULL_AI`   | `full_ai`     |
| `ADMIN`     | `admin`       |

| `AiAccessLevel` | Stored value |
|----------------|--------------|
| `NONE`         | `none`       |
| `LIGHT`        | `light`      |
| `HEAVY`        | `heavy`      |

Helpers: **`normalize_plan_code`**, **`normalize_ai_access_level`** (invalid → `None`).

`FeatureTier` in **`app.core.feature_access`** (`free`, `light_ai`, `heavy_ai`) classifies **features**; plan/access enums classify **accounts**. Map between them inside `_non_admin_ai_entitled` when you add real rules.

## Feature tiers (`app.core.feature_access`)

| Tier | Meaning |
|------|---------|
| `FREE` | Core surfaces: monitoring, dashboards, charts, groups, portfolios, entities, macro/entity data, heuristic analysis, non-LLM reports, community feed, RSS ingest, research workspace. |
| `LIGHT_AI` | Lighter LLM usage (e.g. keyword suggestions, timeline AI summary). |
| `HEAVY_AI` | Document LLM analysis, AI schedules (`ai_alert`, `ai_report`, `general_alert`), and similar high-cost workflows. |

Canonical names live in `FeatureKey` and `FEATURE_TIER_MAP` in `backend/app/core/feature_access.py`.

## API / code flow

- **`get_feature_tier(feature_name)`** — returns `FeatureTier` for a registered key (unknown keys raise `KeyError`).
- **`can_access_feature(user, feature_name)`** — `True` if admin; else `True` for `FREE` tier keys; else uses **`_non_admin_ai_entitled`** (today always `False` for non-admins on LIGHT/HEAVY).
- **HTTP dependencies** — `require_feature(feature_name)` in `app.api.deps` returns a FastAPI dependency that returns 403 with the same user-facing message as before.

Legacy helper **`can_use_paid_ai`** remains as a **HEAVY_AI-oriented** compatibility alias (`DOCUMENT_LLM_ANALYSIS`). Prefer `can_access_feature` with the specific `FeatureKey` at call sites.

## Credit / metering stubs (`app.core.feature_billing_hooks`)

| Function | Now | Later |
|----------|-----|--------|
| `can_consume_feature` | Always `True` | Enforce balance/quota before LLM |
| `estimate_feature_credit_cost` | Always `0` | Feature-specific pricing |
| `charge_feature_credits` | No-op | Decrement balance + ledger write |

## User fields (future billing)

On `users` (SQLAlchemy model + startup schema patch):

| Column | Default (`app.core.plan_entitlements`) | Purpose |
|--------|------------------------------------------|---------|
| `plan_code` | `PlanCode.FREE` | Commercial / internal plan slug. |
| `ai_access_level` | `AiAccessLevel.NONE` | Coarse AI band for the account. |
| `credits_balance` | (existing) | Balance for metered usage. |

Exposed on `GET /api/auth/me` (`MeResponse`). They do **not** yet drive gating beyond defaults.

## Admin override

**Admins bypass all tier checks** inside `can_access_feature`. Future subscription logic should still treat admin as full access unless product policy explicitly changes.

## Usage ledger (design only)

See **`docs/ai_usage_ledger.md`** and **`app/schemas/ai_usage_ledger_proposed.py`** (`AiUsageLedgerRow`).

## Plugging in billing later

1. Implement entitlement in **`_non_admin_ai_entitled`** using **`PlanCode`** / **`AiAccessLevel`** and credits.
2. Replace stubs in **`feature_billing_hooks`** and write ledger rows.
3. Add migrations for **`ai_usage_ledger`** when ready.
4. Optionally add Stripe webhooks to update `plan_code`, `ai_access_level`, and `credits_balance`.
5. Keep route and worker checks on **`can_access_feature`** / **`require_feature`**.

## Related docs

- `docs/admin_only_ai_gating.md` — historical admin-only AI policy and endpoint inventory.
- `docs/ai_usage_ledger.md` — proposed usage log schema.
