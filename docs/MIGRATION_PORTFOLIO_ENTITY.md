# Migration: Keyword Groups → Portfolio / Entity

## Current state

- **Schedules**: `MonitoringSchedule.group_ids_csv` → worker runs per `KeywordGroup`, writes `IndexPoint(group_id)`, creates Report with `group_snapshot` and `group_id` in payload.
- **Reports**: `Report.kind` = group_snapshot | info_24h | keyword_daily; payload holds `group_id` for group_snapshot.
- **Research**: `ResearchProject.layout_config` (dict); no entity_id or chart_type in schema. UI assumes groups.
- **Entity Data**: New Portfolio/Entity UI and APIs exist; schedules and reports still use groups only.

## Phase 1 — Schedule / Report (entity support)

1. **Model**: Add `entity_ids_csv` to `MonitoringSchedule` (default "" = legacy). For existing DBs run: `ALTER TABLE monitoring_schedules ADD COLUMN IF NOT EXISTS entity_ids_csv TEXT NOT NULL DEFAULT '';`
2. **Schema**: Add `entity_ids: list[str]` to ScheduleCreate and ScheduleOut; API accepts and returns entity_ids.
3. **Routes**: On create/read, map between `entity_ids_csv` and `entity_ids`; validate entity ownership.
4. **Worker**: If `entity_ids_csv` non-empty, resolve entities (PortfolioEntity), for each entity generate Report with kind `entity_snapshot`, payload with entity_id, portfolio_id, name, instrument, terms. Keep existing group_ids flow unchanged.
5. **Reporting**: Add `build_entity_snapshot_markdown` and use for entity_snapshot reports.

## Phase 2 — Entity Detail page

1. **API**: Add `GET /api/entities/{entity_id}` (single entity with portfolio name, instrument, terms).
2. **Route**: New page `app/dashboard/entities/[id]/page.tsx`.
3. **Page content**: Header (name, portfolio, instrument, asset type), Terms (list + edit + AI), Price chart (instrument), Add Chart placeholders (Price, Search Volume, Coverage Volume, Sentiment, Quadrant).
4. **Entity list**: Add "View" link on each entity card → `/dashboard/entities/[id]`.

## Phase 3 — Research (entity/chart compatibility)

1. **Data model**: No new tables; `ResearchProject.layout_config` can store `charts: [{ entity_id?, chart_type?, market_item? }]`.
2. **Schemas**: Added `ResearchChartItem` in `schemas/research.py`; `ResearchProjectOut.layout_config` documented. Projects can store entity_id and chart_type in layout_config.
3. **APIs**: No breaking changes; research project create/update already accept layout_config; frontend can send layout_config.charts for entity-based charts.

## Backward compatibility

- Old schedules (group_ids only) continue to run as today.
- New schedules can use entity_ids only or (if we allow) both; worker prefers entity_ids when present.
- Reports: existing kinds unchanged; new kind `entity_snapshot` for entity-based runs.
- Research: additive; existing projects keep current layout_config; new projects can store entity/chart refs.
