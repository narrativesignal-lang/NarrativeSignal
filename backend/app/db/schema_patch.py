"""Startup-safe schema patches for existing DBs (no Alembic). Safe to run on every boot."""

from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


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


def run_schema_patches(engine) -> None:
    """Run all startup-safe schema patches. Call from API and worker startup."""
    ensure_active_market_pool_table(engine)
    ensure_macro_news_list_snapshots_table(engine)
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
    ensure_macro_events_lifecycle_columns(engine)
