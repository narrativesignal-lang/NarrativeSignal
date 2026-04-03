"""Startup-safe schema patches for existing DBs (no Alembic). Safe to run on every boot."""

from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

def _ensure_fk_cascade_postgres(
    engine,
    *,
    table: str,
    column: str,
    ref_table: str,
    ref_column: str = "id",
) -> None:
    """
    Ensure FK(table.column -> ref_table.ref_column) is ON DELETE CASCADE (Postgres only).
    Safe to run repeatedly; no-op if already cascade.
    """
    if getattr(engine.dialect, "name", "") != "postgresql":
        return
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT con.conname AS name, con.confdeltype AS deltype
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    JOIN pg_class refrel ON refrel.oid = con.confrelid
                    WHERE con.contype = 'f'
                      AND rel.relname = :table
                      AND refrel.relname = :ref_table
                      AND EXISTS (
                        SELECT 1
                        FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k.attnum
                        WHERE att.attname = :column
                      )
                    LIMIT 1
                    """
                ),
                {"table": table, "ref_table": ref_table, "column": column},
            ).mappings().first()
            if not row:
                return
            if str(row.get("deltype") or "").lower() == "c":
                return
            cname = str(row["name"])
            conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{cname}"'))
            conn.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'ADD CONSTRAINT "{cname}" FOREIGN KEY ("{column}") '
                    f'REFERENCES "{ref_table}"("{ref_column}") ON DELETE CASCADE'
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch FK cascade failed %s.%s -> %s.%s: %s", table, column, ref_table, ref_column, e)


def ensure_user_owned_fk_cascades(engine) -> None:
    """
    User is top-level owner. Ensure clearly user-owned foreign keys cascade on delete.
    (Postgres-only constraint patch; SQLite/local may require rebuild.)
    """
    # Core ownership chain: users -> portfolios -> portfolio_entities -> entity_terms
    _ensure_fk_cascade_postgres(engine, table="portfolios", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="portfolio_entities", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="portfolio_entities", column="portfolio_id", ref_table="portfolios")
    _ensure_fk_cascade_postgres(engine, table="entity_terms", column="entity_id", ref_table="portfolio_entities")

    # Other clearly user-owned tables (non-null user_id)
    _ensure_fk_cascade_postgres(engine, table="reports", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="credit_ledger", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="monitoring_schedules", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="monitoring_runs", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="triggered_alerts", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="research_folders", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="research_projects", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="keyword_groups", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="keyword_group_rss_feeds", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="entity_configs", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="macro_indices", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="macro_categories", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="macro_data_sources", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="entities", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="source_documents", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="community_submissions", column="user_id", ref_table="users")
    _ensure_fk_cascade_postgres(engine, table="community_data_requests", column="user_id", ref_table="users")


def ensure_monitoring_schedule_entity_column(engine) -> None:
    """
    Add entity_ids_csv to monitoring_schedules if missing (entity-based scheduling).
    Safe for existing DBs: uses IF NOT EXISTS. Does not touch group_ids_csv.
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_schedules "
                    "ADD COLUMN IF NOT EXISTS entity_ids_csv TEXT NOT NULL DEFAULT ''"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch monitoring_schedules.entity_ids_csv failed (may already exist): %s", e)


def ensure_entity_related_instruments_table(engine) -> None:
    """
    Create entity_related_instruments table if missing (related instruments per entity).
    Safe for existing DBs.
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS entity_related_instruments (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NOT NULL REFERENCES portfolio_entities(id) ON DELETE CASCADE,
                        instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                        display_order INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(entity_id, instrument_id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entity_related_instruments_entity_id ON entity_related_instruments(entity_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entity_related_instruments_instrument_id ON entity_related_instruments(instrument_id)"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_related_instruments failed: %s", e)


def ensure_entity_chart_layout_column(engine) -> None:
    """Add chart_layout JSONB to portfolio_entities if missing (Add Chart workspace persistence)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE portfolio_entities "
                    "ADD COLUMN IF NOT EXISTS chart_layout JSONB"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch portfolio_entities.chart_layout failed: %s", e)


def ensure_instrument_columns(engine) -> None:
    """
    Add optional columns to instruments for richer metadata.

    Safe for existing DBs: uses IF NOT EXISTS and does not modify existing data.
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE instruments "
                    "ADD COLUMN IF NOT EXISTS description TEXT"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE instruments "
                    "ADD COLUMN IF NOT EXISTS country VARCHAR(4)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE instruments "
                    "ADD COLUMN IF NOT EXISTS source_priority INTEGER"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE instruments "
                    "ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch instruments extra columns failed: %s", e)


def ensure_research_setup_snapshot_name(engine) -> None:
    """Add optional name to research_setup_snapshots for user-facing label."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE research_setup_snapshots "
                    "ADD COLUMN IF NOT EXISTS name VARCHAR(120)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch research_setup_snapshots.name failed: %s", e)


def ensure_entity_daily_metrics_timestamps(engine) -> None:
    """Add created_at / updated_at to entity_daily_metrics for existing DBs."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_daily_metrics timestamps failed: %s", e)


def ensure_entity_daily_metrics_metric_columns(engine) -> None:
    """Add Phase 2 metric fields to entity_daily_metrics for existing DBs."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS sentiment_score DOUBLE PRECISION"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_daily_metrics metric columns failed: %s", e)


def ensure_entity_daily_metrics_search_volume_split(engine) -> None:
    """Target vs narrative Google Trends columns (no mixed search_trend writes going forward)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS target_search_volume DOUBLE PRECISION"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS keywords_search_volume DOUBLE PRECISION"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS target_search_volume_source VARCHAR(20)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE entity_daily_metrics "
                    "ADD COLUMN IF NOT EXISTS keywords_search_volume_source VARCHAR(20)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_daily_metrics search volume split failed: %s", e)
        return
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE entity_daily_metrics SET keywords_search_volume = search_trend, "
                    "keywords_search_volume_source = COALESCE(NULLIF(TRIM(search_trend_source), ''), 'google_trends') "
                    "WHERE keywords_search_volume IS NULL AND search_trend IS NOT NULL "
                    "AND LOWER(COALESCE(search_trend_source, '')) IN ('google_trends', 'real')"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch backfill keywords_search_volume from search_trend failed: %s", e)


def ensure_monitoring_schedule_ai_columns(engine) -> None:
    """Add schedule_type, label, model, impact_threshold, linked_assets_csv for AI Alert/Report."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_schedules "
                    "ADD COLUMN IF NOT EXISTS schedule_type VARCHAR(40) NOT NULL DEFAULT 'standard_monitor'"
                )
            )
            conn.execute(
                text("ALTER TABLE monitoring_schedules ADD COLUMN IF NOT EXISTS label VARCHAR(120)")
            )
            conn.execute(
                text("ALTER TABLE monitoring_schedules ADD COLUMN IF NOT EXISTS model VARCHAR(40)")
            )
            conn.execute(
                text("ALTER TABLE monitoring_schedules ADD COLUMN IF NOT EXISTS impact_threshold INTEGER")
            )
            conn.execute(
                text(
                    "ALTER TABLE monitoring_schedules "
                    "ADD COLUMN IF NOT EXISTS linked_assets_csv TEXT NOT NULL DEFAULT ''"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch monitoring_schedules AI columns failed: %s", e)


def ensure_report_label_columns(engine) -> None:
    """Add label and schedule_type to reports for filtering."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS label VARCHAR(120)")
            )
            conn.execute(
                text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS schedule_type VARCHAR(40)")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch reports label/schedule_type failed: %s", e)


def ensure_users_plan_and_ai_level_columns(engine) -> None:
    """Future billing: plan_code and ai_access_level (defaults preserve existing behavior)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_code VARCHAR(64) NOT NULL DEFAULT 'free'")
            )
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_access_level VARCHAR(32) NOT NULL DEFAULT 'none'"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users plan_code/ai_access_level failed: %s", e)


def ensure_users_paid_access_column(engine) -> None:
    """Paid-feature flag (e.g. event timeline): requires paid_access + credits; admins bypass in app code."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_access BOOLEAN NOT NULL DEFAULT FALSE")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.paid_access failed: %s", e)


def ensure_users_profile_name_column(engine) -> None:
    """Add profile_name for editable display name on Profile page."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_name VARCHAR(120) NOT NULL DEFAULT ''"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.profile_name failed: %s", e)


def ensure_users_is_admin_column(engine) -> None:
    """Add is_admin to users for admin/test account. Dev bootstrap only."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.is_admin failed: %s", e)


def ensure_users_username_token_version(engine) -> None:
    """Add username (unique) and token_version for single-session enforcement."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(80)")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.username column failed: %s", e)
    try:
        with engine.connect() as conn:
            # Backfill: admin -> 'admin', others -> email (guarantees uniqueness)
            conn.execute(
                text("""
                    UPDATE users SET username = CASE
                        WHEN email = 'admin@internal.test' THEN 'admin'
                        ELSE LOWER(SUBSTRING(email FROM 1 FOR 80))
                    END
                    WHERE username IS NULL OR username = ''
                """)
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.username backfill failed: %s", e)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ALTER COLUMN username SET NOT NULL"))
            conn.commit()
    except Exception:
        pass  # Column may already be NOT NULL
    try:
        with engine.connect() as conn:
            conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_lower ON users (LOWER(TRIM(username)))")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users username unique index failed: %s", e)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch users.token_version failed: %s", e)


def ensure_community_tables(engine) -> None:
    """Create community_submissions and community_data_requests tables."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS community_submissions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        category VARCHAR(60) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        problem_solves TEXT NOT NULL DEFAULT '',
                        platform_data_used TEXT NOT NULL DEFAULT '',
                        has_data_source BOOLEAN NOT NULL DEFAULT FALSE,
                        data_source_access TEXT NOT NULL DEFAULT '',
                        contact_info VARCHAR(320) NOT NULL DEFAULT '',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS community_data_requests (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        requested_data_name VARCHAR(200) NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        use_case TEXT NOT NULL DEFAULT '',
                        source_known BOOLEAN NOT NULL DEFAULT FALSE,
                        how_to_obtain TEXT NOT NULL DEFAULT '',
                        source_details TEXT NOT NULL DEFAULT '',
                        contact_info VARCHAR(320) NOT NULL DEFAULT '',
                        priority VARCHAR(40) NOT NULL DEFAULT 'medium',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_community_submissions_user_id ON community_submissions(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_community_data_requests_user_id ON community_data_requests(user_id)"))
            conn.commit()
            conn.execute(
                text(
                    "ALTER TABLE community_data_requests "
                    "ADD COLUMN IF NOT EXISTS contact_info VARCHAR(320) NOT NULL DEFAULT ''"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch community tables failed: %s", e)


def ensure_alerts_table(engine) -> None:
    """Create triggered_alerts table for AI Alert MVP."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS triggered_alerts (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        schedule_id UUID REFERENCES monitoring_schedules(id) ON DELETE SET NULL,
                        schedule_type VARCHAR(40) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        body_markdown TEXT NOT NULL DEFAULT '',
                        impact_score INTEGER,
                        payload JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_triggered_alerts_user_id ON triggered_alerts(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_triggered_alerts_created_at ON triggered_alerts(created_at DESC)"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch triggered_alerts failed: %s", e)


def ensure_macro_events_lifecycle_columns(engine) -> None:
    """
    Add created_at / updated_at for macro_events (retention auditing & future policies).
    Backfill from timestamp for existing rows.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE macro_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
            conn.execute(text("ALTER TABLE macro_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch macro_events lifecycle add columns failed: %s", e)
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE macro_events SET created_at = timestamp WHERE created_at IS NULL"))
            conn.execute(text("UPDATE macro_events SET updated_at = timestamp WHERE updated_at IS NULL"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch macro_events lifecycle backfill failed: %s", e)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE macro_events ALTER COLUMN created_at SET DEFAULT now()"))
            conn.execute(
                text("ALTER TABLE macro_events ALTER COLUMN created_at SET NOT NULL")
            )
            conn.execute(text("ALTER TABLE macro_events ALTER COLUMN updated_at SET DEFAULT now()"))
            conn.execute(
                text("ALTER TABLE macro_events ALTER COLUMN updated_at SET NOT NULL")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch macro_events lifecycle NOT NULL failed (may already be applied): %s", e)


def ensure_macro_news_list_snapshots_table(engine) -> None:
    """Cache-first macro news list: one JSONB blob per category."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS macro_news_list_snapshots (
                        category VARCHAR(32) PRIMARY KEY,
                        items JSONB NOT NULL DEFAULT '[]'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch macro_news_list_snapshots failed: %s", e)


def ensure_active_market_pool_table(engine) -> None:
    """Global dynamic Twelve warm pool (symbol + access timestamps; soft-disable)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS active_market_pool (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        symbol VARCHAR(40) NOT NULL,
                        source_type VARCHAR(32) NOT NULL DEFAULT 'active_pool',
                        last_accessed_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        is_enabled BOOLEAN NOT NULL DEFAULT true,
                        CONSTRAINT uq_active_market_pool_symbol UNIQUE (symbol)
                    )
                    """
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_active_market_pool_enabled ON active_market_pool (is_enabled)")
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_active_market_pool_source_type ON active_market_pool (source_type)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch active_market_pool failed: %s", e)


def ensure_market_snapshot_provider_columns(engine) -> None:
    """Add provider_source columns for quote/ohlcv lineage visibility."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE market_quote_snapshots "
                    "ADD COLUMN IF NOT EXISTS provider_source VARCHAR(32)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ohlcv_snapshots "
                    "ADD COLUMN IF NOT EXISTS provider_source VARCHAR(32)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch market snapshot provider_source columns failed: %s", e)


def ensure_entity_analysis_table(engine) -> None:
    """Massive isolated analysis table (must not leak into display tables)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS entity_analysis (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NOT NULL UNIQUE REFERENCES portfolio_entities(id) ON DELETE CASCADE,
                        event_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                        anomaly_flag BOOLEAN NOT NULL DEFAULT FALSE,
                        narrative_strength DOUBLE PRECISION NOT NULL DEFAULT 0,
                        last_analysis_time TIMESTAMPTZ NOT NULL DEFAULT now(),
                        analysis_source VARCHAR(40) NOT NULL DEFAULT 'massive_light',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entity_analysis_entity_id ON entity_analysis(entity_id)"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_analysis failed: %s", e)


def ensure_massive_ai_explanation_cache_table(engine) -> None:
    """Cache for OpenAI entity chart explanations (legacy table name; not Massive market data)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS massive_ai_explanation_cache (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NOT NULL REFERENCES portfolio_entities(id) ON DELETE CASCADE,
                        feature_type VARCHAR(48) NOT NULL,
                        fingerprint VARCHAR(64) NOT NULL,
                        window_start TIMESTAMPTZ NOT NULL,
                        window_end TIMESTAMPTZ NOT NULL,
                        payload JSONB NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        model_label VARCHAR(120) NULL,
                        CONSTRAINT uq_massive_ai_cache_entity_feature_fp UNIQUE (entity_id, feature_type, fingerprint)
                    )
                    """
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_massive_ai_cache_entity ON massive_ai_explanation_cache(entity_id)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_massive_ai_cache_feature ON massive_ai_explanation_cache(feature_type)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_massive_ai_cache_fp ON massive_ai_explanation_cache(fingerprint)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_massive_ai_cache_expires ON massive_ai_explanation_cache(expires_at)")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch massive_ai_explanation_cache failed: %s", e)


def ensure_entity_triple_signal_daily_table(engine) -> None:
    """Triple signal normalized metrics table per entity/day."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS entity_triple_signal_daily (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NOT NULL REFERENCES portfolio_entities(id) ON DELETE CASCADE,
                        metric_date DATE NOT NULL,
                        trading_activity DOUBLE PRECISION NOT NULL DEFAULT 0,
                        news_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
                        search_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
                        last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
                        CONSTRAINT uq_entity_triple_signal_day UNIQUE (entity_id, metric_date)
                    )
                    """
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_entity_triple_signal_daily_entity_date ON entity_triple_signal_daily(entity_id, metric_date)")
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_triple_signal_daily failed: %s", e)


def ensure_massive_backfill_queue_table(engine) -> None:
    """Queue for MassiveBackfillLoop (low-frequency market data backfill)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS massive_backfill_queue (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NULL,
                        symbol VARCHAR(40) NOT NULL,
                        asset_class VARCHAR(24) NULL,
                        need_quote BOOLEAN NOT NULL DEFAULT FALSE,
                        need_ohlcv BOOLEAN NOT NULL DEFAULT FALSE,
                        priority INTEGER NOT NULL DEFAULT 0,
                        source_reason VARCHAR(40) NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        last_attempt_at TIMESTAMPTZ NULL,
                        next_attempt_at TIMESTAMPTZ NULL,
                        provider_last_used VARCHAR(40) NULL,
                        last_error TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        CONSTRAINT uq_massive_backfill_symbol_need UNIQUE (symbol, need_quote, need_ohlcv)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_massive_backfill_queue_symbol ON massive_backfill_queue(symbol)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_massive_backfill_queue_status ON massive_backfill_queue(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_massive_backfill_queue_next_attempt ON massive_backfill_queue(next_attempt_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_massive_backfill_queue_entity ON massive_backfill_queue(entity_id)"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch massive_backfill_queue failed: %s", e)


def ensure_system_runtime_flags_table(engine) -> None:
    """Admin-controlled runtime flags (no restart needed)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS system_runtime_flags (
                        key VARCHAR(80) PRIMARY KEY,
                        value_bool BOOLEAN NOT NULL DEFAULT FALSE,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_by VARCHAR(80) NULL
                    )
                    """
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch system_runtime_flags failed: %s", e)


def ensure_system_runtime_logs_table(engine) -> None:
    """Tiny admin-visible runtime log buffer (bounded; not a full logging system)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS system_runtime_logs (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        level VARCHAR(16) NOT NULL DEFAULT 'info',
                        category VARCHAR(24) NOT NULL DEFAULT 'system',
                        job_name VARCHAR(80) NULL,
                        provider VARCHAR(40) NULL,
                        status VARCHAR(16) NULL,
                        message TEXT NOT NULL DEFAULT '',
                        disabled_by_runtime_flag BOOLEAN NOT NULL DEFAULT FALSE,
                        no_provider_call BOOLEAN NOT NULL DEFAULT FALSE,
                        request_count INTEGER NULL,
                        fallback_count INTEGER NULL,
                        symbol_count INTEGER NULL
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_runtime_logs_created_at ON system_runtime_logs(created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_runtime_logs_category ON system_runtime_logs(category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_runtime_logs_level ON system_runtime_logs(level)"))
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch system_runtime_logs failed: %s", e)


def ensure_normalized_news_unique_url(engine) -> None:
    """Prevent duplicate normalized docs by canonical_url (safe when table is empty/small)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_normalized_news_canonical_url "
                    "ON normalized_news_documents (canonical_url)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch normalized_news_documents unique url failed: %s", e)


def ensure_entity_sentiment_baselines_table(engine) -> None:
    """Cache baseline tone per entity+window (for incremental sentiment series)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS entity_sentiment_baselines (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_id UUID NOT NULL REFERENCES portfolio_entities(id) ON DELETE CASCADE,
                        window_start DATE NOT NULL,
                        window_end DATE NOT NULL,
                        bucket_step_days INTEGER NOT NULL DEFAULT 7,
                        baseline_score DOUBLE PRECISION NOT NULL,
                        baseline_label VARCHAR(16) NOT NULL,
                        confidence DOUBLE PRECISION NULL,
                        provider VARCHAR(32) NOT NULL DEFAULT 'unknown',
                        model VARCHAR(64) NOT NULL DEFAULT 'v1',
                        computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(entity_id, window_start, window_end, bucket_step_days)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_entity_sentiment_baselines_entity_id ON entity_sentiment_baselines(entity_id)"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_entity_sentiment_baseline_entity_window "
                    "ON entity_sentiment_baselines(entity_id, window_start, window_end)"
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning("Schema patch entity_sentiment_baselines failed: %s", e)
def run_schema_patches(engine) -> None:
    """Run all startup-safe schema patches. Call from API and worker startup."""
    ensure_active_market_pool_table(engine)
    ensure_market_snapshot_provider_columns(engine)
    ensure_entity_analysis_table(engine)
    ensure_massive_ai_explanation_cache_table(engine)
    ensure_entity_triple_signal_daily_table(engine)
    ensure_massive_backfill_queue_table(engine)
    ensure_system_runtime_flags_table(engine)
    ensure_system_runtime_logs_table(engine)
    ensure_normalized_news_unique_url(engine)
    ensure_entity_sentiment_baselines_table(engine)
    ensure_macro_news_list_snapshots_table(engine)
    ensure_users_plan_and_ai_level_columns(engine)
    ensure_users_paid_access_column(engine)
    ensure_users_is_admin_column(engine)
    ensure_users_profile_name_column(engine)
    ensure_users_username_token_version(engine)
    ensure_community_tables(engine)
    ensure_monitoring_schedule_entity_column(engine)
    ensure_monitoring_schedule_ai_columns(engine)
    ensure_alerts_table(engine)
    ensure_report_label_columns(engine)
    ensure_entity_related_instruments_table(engine)
    ensure_entity_chart_layout_column(engine)
    ensure_instrument_columns(engine)
    ensure_research_setup_snapshot_name(engine)
    ensure_entity_daily_metrics_timestamps(engine)
    ensure_entity_daily_metrics_metric_columns(engine)
    ensure_entity_daily_metrics_search_volume_split(engine)
    ensure_macro_events_lifecycle_columns(engine)
    ensure_user_owned_fk_cascades(engine)
