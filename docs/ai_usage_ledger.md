# AI usage ledger (proposal — not migrated)

This document proposes a **durable log** for observability, cost attribution, and billing reconciliation.
No table is created in the application yet; see the dataclass mirror in
`backend/app/schemas/ai_usage_ledger_proposed.py`.

## Purpose

- Debug per-user/provider spend and token patterns.
- Drive invoices or credit burns from **recorded** usage rather than estimates only.
- Correlate `feature_key` / `feature_tier` with product analytics.

## Proposed table: `ai_usage_ledger`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | default `gen_random_uuid()` |
| `user_id` | UUID FK → `users.id` | not null |
| `feature_key` | VARCHAR(96) | same vocabulary as `FeatureKey` in `feature_access` |
| `feature_tier` | VARCHAR(24) | `FeatureTier` value: `free`, `light_ai`, `heavy_ai` |
| `provider` | VARCHAR(64) | e.g. `openai`, `gemini` |
| `model` | VARCHAR(120) | provider model id |
| `input_tokens` | INTEGER | nullable for non-token providers |
| `output_tokens` | INTEGER | nullable |
| `estimated_cost` | NUMERIC(18,6) | optional USD or internal cost unit |
| `credits_charged` | INTEGER | internal credits debited for this row (0 until charging exists) |
| `created_at` | TIMESTAMPTZ | not null, default `now()` |

Recommended indexes:

- `(user_id, created_at DESC)` for account history.
- Optional `(feature_key, created_at)` for product rollups.

## Relationship to other pieces

1. **`can_access_feature`** — decides if the call may run (tier + admin).
2. **`can_consume_feature`** (future) — credits/quota gate before the call.
3. **Provider call** — produce token counts / latency.
4. **`charge_feature_credits`** (future) — update balance + insert row (or insert first, then adjust).

Until migrations land, application code can import **`AiUsageLedgerRow`** only for typing or test doubles.
