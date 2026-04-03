"""Portfolio / Entity / Terms / Instrument APIs. User-isolated. Coexists with keyword-groups."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Literal

logger = logging.getLogger(__name__)


def _entity_signal_envelope(last: datetime | None, stale: bool) -> dict[str, str | bool | None]:
    lu = last.isoformat() if last else None
    if last is None:
        return {
            "last_updated_at": None,
            "data_updated_at": None,
            "data_source": "placeholder",
            "loading_state": "warming",
            "message": "Entity metrics are still warming; values shown are placeholders until snapshots arrive.",
            "stale": True,
        }
    if stale:
        return {
            "last_updated_at": lu,
            "data_updated_at": lu,
            "data_source": "stale_fallback",
            "loading_state": "stale",
            "message": None,
            "stale": True,
        }
    return {
        "last_updated_at": lu,
        "data_updated_at": lu,
        "data_source": "snapshot",
        "loading_state": "ready",
        "message": None,
        "stale": False,
    }


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user, require_feature
from app.core.config import settings
from app.core.limits import (
    MAX_ENTITIES_PER_PORTFOLIO,
    MAX_ITEMS_PER_ENTITY,
    MAX_PORTFOLIOS,
    MSG_MAX_ENTITIES,
    MSG_MAX_ITEMS_PER_ENTITY,
    MSG_MAX_PORTFOLIOS,
)
from app.db.session import get_db
from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.data_subscription import OhlcvSnapshot
from app.models.portfolio import EntityRelatedInstrument, EntityTerm, Instrument, Portfolio, PortfolioEntity
from app.models.user import User
from app.services.market_snapshots import schedule_market_snapshot_refresh_for_symbols
from app.services.instrument_search_service import (
    filter_twelve_instrument_search_rows,
    persist_twelve_instrument_rows,
    twelve_row_from_bind_fields,
    twelve_row_identity_key,
    twelve_rows_to_ephemeral_hit_dicts,
    upsert_instrument_from_twelve_symbol_row,
)
from app.services.subscriptions import (
    register_entity_subscriptions,
    register_instrument_quote_subscription,
    remove_entity_subscriptions,
)
from app.services.target_entity_sync import delete_target_entity_record, upsert_target_entity_for_portfolio_entity
from app.services.entity_metrics_pipeline import (
    entity_target_and_narrative_keywords,
    explain_chart_3d_absence,
    explain_search_volumes_absence,
    get_chart_3d_payload,
    get_entity_keywords_search_timeseries,
    get_entity_target_search_timeseries,
    last_keywords_search_success_at,
    last_target_search_success_at,
    sync_entity_search_trend,
)
from app.services.entity_references import remove_entity_from_research_layouts
from app.services.core_data_diag import record_first_paint_envelope, record_snapshot_hit
from app.services.entity_event_timeline import (
    ai_summary_placeholder,
    build_timeline_points,
    get_timeline_window,
    resolve_timeline_asset_class,
)
from app.schemas.entity_timeline import (
    AiSummaryRequest,
    AiSummaryResponse,
    TimelinePointsResponse,
    TimelineWindowResponse,
)
from app.schemas.portfolios import (
    AddRelatedInstrumentBody,
    Chart3DPoint,
    Chart3DSourceStatus,
    ComparisonSeriesLine,
    ComparisonSeriesOut,
    ComparisonSeriesPoint,
    EntityChart3DDataOut,
    EntityCreate,
    EntityDetailOut,
    EntityOut,
    EntityTermOut,
    EntityUpdate,
    InstrumentBindResolve,
    InstrumentSearchHit,
    PortfolioCreate,
    PortfolioOut,
    PortfolioUpdate,
    QuadrantHistoryOut,
    QuadrantHistoryPoint,
    QuadrantOut,
    RelatedInstrumentOut,
    TermCreate,
    TermOut,
    TermsReplace,
    TimeSeriesOut,
    TimeSeriesPoint,
    SentimentSeriesOut,
    SentimentSeriesPoint,
    TrendingOut,
    EntityKeywordsSearchSeriesOut,
    EntityTargetSearchSeriesOut,
    KeywordsSearchPoint,
    TargetSearchPoint,
    EntityMetricPoint,
    EntityMetricSeriesOut,
    TripleSignalSeriesOut,
    InstitutionBiasOut,
    RatingDistributionOut,
    EntityNewsItemOut,
    EntityNewsOut,
)
from app.services.entity_chart_3d import normalize_chart_3d_range
from app.services.entity_metrics_service import get_entity_metric_timeseries
from app.services.entity_news_service import fetch_entity_news
from app.services.entity_sentiment_series_ai import compute_sentiment_series_delta, read_cached_sentiment_series
from app.services.triple_signal_metrics import read_entity_triple_signal_series_aligned
from app.services.narrative_metrics import (
    entity_metric_timeseries_bundle,
    entity_quadrant_current_bundle,
    entity_quadrant_history_bundle,
    entity_trending_bundle,
)
from app.services.runtime_flags import RuntimeFlagKey, ai_feature_enabled
from app.core.feature_access import FeatureKey, can_access_feature

MAX_TERMS = 15
MAX_COMPARISON_INSTRUMENTS = 4
MAX_WORKSPACE_CHARTS = 5
_WORKSPACE_CHART_TYPES = frozenset({
    "technical", "sentiment", "quadrant", "3d",
    "overlay_technical", "overlay_sentiment",
    "split_technical", "split_sentiment",
    "series_search_volume",  # legacy client → keywords on read
    "series_target_search_volume",
    "series_keywords_search_volume",
    "series_coverage_volume",
    "series_triple_signal",
    "metric_momentum",
    "metric_acceleration",
    "metric_momentum_target",
    "metric_acceleration_target",
    "metric_momentum_keywords",
    "metric_acceleration_keywords",
    "analysis_3d", "analysis_institution_bias", "analysis_rating_distribution",
})

router = APIRouter()


def _looks_like_ephemeral_instrument_id(raw: str) -> bool:
    return (raw or "").strip().startswith("ext-pending-")


def _resolve_instrument_id_for_bind(
    db: Session,
    *,
    instrument_id: str | None,
    resolve: InstrumentBindResolve | None,
    log_context: str,
) -> uuid.UUID | None:
    """
    Map search selection to a persisted Instrument UUID.
    - Valid UUID + active row → local_db_hit
    - ext-pending-* (+ instrument_resolve) → upsert then external_fallback_resolved
    - empty id + instrument_resolve → persist from resolve only
    """
    raw = (instrument_id or "").strip()
    if not raw and resolve is not None:
        try:
            row = twelve_row_from_bind_fields(
                symbol=resolve.symbol,
                asset_class=resolve.asset_class,
                exchange=resolve.exchange,
                display_name=resolve.display_name,
            )
            inst, created = upsert_instrument_from_twelve_symbol_row(db, row, provider="external_api")
            logger.info(
                "bind_instrument external_fallback_resolved context=%s instrument_id=%s symbol=%s "
                "created=%s mode=resolve_only",
                log_context,
                inst.id,
                inst.symbol,
                created,
            )
            return inst.id
        except Exception as e:
            logger.warning(
                "bind_instrument external_fallback_persist_failed context=%s symbol=%s err=%s",
                log_context,
                resolve.symbol,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail="Could not save instrument. Please try again.",
            ) from e

    if not raw:
        return None

    try:
        uid = uuid.UUID(raw)
    except ValueError:
        uid = None

    if uid is not None:
        inst = db.scalar(select(Instrument).where(Instrument.id == uid, Instrument.is_active.is_(True)))
        if inst:
            logger.info(
                "bind_instrument local_db_hit context=%s instrument_id=%s symbol=%s",
                log_context,
                uid,
                inst.symbol,
            )
            return uid
        logger.warning(
            "bind_instrument bind_failed context=%s reason=not_found instrument_id=%s",
            log_context,
            raw,
        )
        raise HTTPException(status_code=404, detail="Instrument not found")

    if not _looks_like_ephemeral_instrument_id(raw):
        logger.warning(
            "bind_instrument bind_failed context=%s reason=invalid_instrument_id instrument_id=%s",
            log_context,
            raw,
        )
        raise HTTPException(status_code=400, detail="Invalid instrument_id")

    if resolve is None:
        logger.warning(
            "bind_instrument bind_failed context=%s reason=missing_instrument_resolve instrument_id=%s",
            log_context,
            raw,
        )
        raise HTTPException(
            status_code=400,
            detail="instrument_resolve is required for this instrument selection",
        )
    try:
        row = twelve_row_from_bind_fields(
            symbol=resolve.symbol,
            asset_class=resolve.asset_class,
            exchange=resolve.exchange,
            display_name=resolve.display_name,
        )
        inst, created = upsert_instrument_from_twelve_symbol_row(db, row, provider="external_api")
        logger.info(
            "bind_instrument external_fallback_resolved context=%s instrument_id=%s symbol=%s created=%s",
            log_context,
            inst.id,
            inst.symbol,
            created,
        )
        return inst.id
    except Exception as e:
        logger.warning(
            "bind_instrument external_fallback_persist_failed context=%s symbol=%s err=%s",
            log_context,
            resolve.symbol,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Could not save instrument. Please try again.",
        ) from e


def _normalize_chart_layout(layout: dict) -> dict:
    """
    Sanitize entity chart_layout for JSONB.
    When workspace_charts is present, cap count, validate types, ensure ids, trim blockHeights.
    """
    out = dict(layout)
    out["version"] = 2
    if "workspace_charts" not in out:
        return out
    raw_blocks = out.get("workspace_charts")
    if not isinstance(raw_blocks, list):
        out["workspace_charts"] = []
        return out
    cleaned: list[dict] = []
    for i, b in enumerate(raw_blocks[:MAX_WORKSPACE_CHARTS]):
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t not in _WORKSPACE_CHART_TYPES:
            continue
        bid = b.get("id")
        if not isinstance(bid, str) or not str(bid).strip():
            bid = f"chart-{t}-{i}"
        else:
            bid = str(bid).strip()
        title = b.get("title")
        if title is not None:
            if not isinstance(title, str):
                title = None
            else:
                title = title.strip() or None
        entry: dict = {"id": bid, "type": t}
        if title is not None:
            entry["title"] = title
        cleaned.append(entry)
    out["workspace_charts"] = cleaned
    valid_ids = {x["id"] for x in cleaned}
    bh = out.get("blockHeights")
    if isinstance(bh, dict):
        new_bh: dict[str, float] = {}
        for k, v in bh.items():
            ks = str(k)
            if ks not in valid_ids:
                continue
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                fv = float(v)
                if fv == fv:  # not NaN
                    new_bh[ks] = fv
        out["blockHeights"] = new_bh
    return out


@router.get("/entities/{entity_id}/metric-series/{metric_name}", response_model=EntityMetricSeriesOut)
def get_entity_metric_series(
    entity_id: str,
    metric_name: str,
    chart_range: str = Query("3m", alias="range", description="1m | 3m | 6m"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityMetricSeriesOut:
    eid = uuid.UUID(entity_id)
    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rk = normalize_chart_3d_range(chart_range)
    try:
        points = get_entity_metric_timeseries(db, entity.id, metric_name, range_key=rk)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return EntityMetricSeriesOut(
        entity_id=str(entity.id),
        metric=metric_name,
        range=rk,
        points=[EntityMetricPoint(date=str(p["date"]), value=float(p["value"])) for p in points],
    )


def _norm(t: str) -> str:
    return (t or "").strip().lower()


def _sanitize(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        n = _norm(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:MAX_TERMS]


def _entity_out(e: PortfolioEntity) -> EntityOut:
    inst = None
    if e.instrument_id and e.instrument:
        inst = InstrumentSearchHit(
            id=str(e.instrument.id),
            symbol=e.instrument.symbol,
            display_name=e.instrument.display_name,
            asset_class=e.instrument.asset_class,
            market=e.instrument.market,
        )
    return EntityOut(
        id=str(e.id),
        portfolio_id=str(e.portfolio_id),
        name=e.name,
        instrument_id=str(e.instrument_id) if e.instrument_id else None,
        instrument=inst,
        terms=[EntityTermOut(id=str(t.id), term=t.term, normalized_term=t.normalized_term, created_at=t.created_at) for t in e.terms],
        chart_layout=e.chart_layout,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


@router.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[PortfolioOut]:
    rows = db.scalars(
        select(Portfolio).where(Portfolio.user_id == current_user.id).order_by(Portfolio.updated_at.desc())
    ).all()
    return [PortfolioOut(id=str(p.id), name=p.name, description=p.description, created_at=p.created_at, updated_at=p.updated_at) for p in rows]


@router.post("/portfolios", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioOut:
    n = db.scalar(select(func.count()).select_from(Portfolio).where(Portfolio.user_id == current_user.id))
    if n and n >= MAX_PORTFOLIOS:
        raise HTTPException(status_code=400, detail=MSG_MAX_PORTFOLIOS)
    p = Portfolio(user_id=current_user.id, name=payload.name, description=payload.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return PortfolioOut(id=str(p.id), name=p.name, description=p.description, created_at=p.created_at, updated_at=p.updated_at)


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: str,
    payload: PortfolioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioOut:
    pid = uuid.UUID(portfolio_id)
    p = db.scalar(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == current_user.id))
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.name is not None:
        p.name = payload.name
    if payload.description is not None:
        p.description = payload.description
    db.commit()
    db.refresh(p)
    return PortfolioOut(id=str(p.id), name=p.name, description=p.description, created_at=p.created_at, updated_at=p.updated_at)


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_200_OK)
def delete_portfolio(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    pid = uuid.UUID(portfolio_id)
    p = db.scalar(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == current_user.id))
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(p)
    db.commit()


@router.get("/portfolios/{portfolio_id}/entities", response_model=list[EntityOut])
def list_entities(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EntityOut]:
    pid = uuid.UUID(portfolio_id)
    port = db.scalar(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == current_user.id))
    if not port:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    entities = db.scalars(select(PortfolioEntity).where(PortfolioEntity.portfolio_id == pid).order_by(PortfolioEntity.updated_at.desc())).all()
    return [_entity_out(e) for e in entities]


@router.get("/entities/{entity_id}", response_model=EntityDetailOut)
def get_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityDetailOut:
    """Get a single entity by id with portfolio name (for detail/workspace page)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(
            selectinload(PortfolioEntity.portfolio),
            selectinload(PortfolioEntity.instrument),
            selectinload(PortfolioEntity.terms),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    out = _entity_out(entity)
    portfolio_name = entity.portfolio.name if entity.portfolio else "—"
    return EntityDetailOut(**out.model_dump(), portfolio_name=portfolio_name)


@router.get("/entities/{entity_id}/news", response_model=EntityNewsOut)
def get_entity_news(
    entity_id: str,
    mode: Literal["target", "keywords"] = Query("target"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityNewsOut:
    """Google News RSS for this entity (target = instrument/name; keywords = saved terms). Cached ~10m."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(selectinload(PortfolioEntity.instrument), selectinload(PortfolioEntity.terms))
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rows, query, err, cached = fetch_entity_news(
        entity_id=entity_id,
        entity=entity,
        mode=mode,
        limit=24,
    )
    items = [EntityNewsItemOut(**row) for row in rows if isinstance(row, dict)]
    logger.info(
        "entity_news_served entity_id=%s mode=%s query=%s item_count=%s cached=%s error=%s",
        entity_id,
        mode,
        (query or "")[:500],
        len(items),
        cached,
        err or "-",
    )
    return EntityNewsOut(mode=mode, query=query, items=items, cached=cached, error=err)


@router.post("/entities", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
def create_entity(
    payload: EntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityOut:
    pid = uuid.UUID(payload.portfolio_id)
    port = db.scalar(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == current_user.id))
    if not port:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    n = db.scalar(select(func.count()).select_from(PortfolioEntity).where(PortfolioEntity.portfolio_id == pid))
    if n and n >= MAX_ENTITIES_PER_PORTFOLIO:
        raise HTTPException(status_code=400, detail=MSG_MAX_ENTITIES)
    inst_id: uuid.UUID | None = None
    if payload.instrument_id is not None or payload.instrument_resolve is not None:
        try:
            inst_id = _resolve_instrument_id_for_bind(
                db,
                instrument_id=payload.instrument_id,
                resolve=payload.instrument_resolve,
                log_context="create_entity",
            )
        except HTTPException:
            logger.warning("bind_instrument bind_failed context=create_entity (HTTP error)")
            raise
    warm_symbol: str | None = None
    e = PortfolioEntity(user_id=current_user.id, portfolio_id=pid, name=payload.name, instrument_id=inst_id)
    db.add(e)
    db.flush()
    for norm in _sanitize(payload.terms or []):
        db.add(EntityTerm(entity_id=e.id, term=norm, normalized_term=norm))
    register_entity_subscriptions(db, current_user.id, e.id)
    if inst_id:
        inst = db.get(Instrument, inst_id)
        if inst and inst.symbol:
            register_instrument_quote_subscription(db, current_user.id, inst.symbol.strip())
            warm_symbol = inst.symbol.strip()
    if payload.terms:
        # Phase-2: ensure every valid-terms entity has initial metric rows immediately.
        rows_synced = sync_entity_search_trend(db, e.id, timeframe="today 3-m")
        logger.info("entity created initial metrics synced entity_id=%s rows=%d", e.id, rows_synced)
    upsert_target_entity_for_portfolio_entity(db, e, name=payload.name)
    db.commit()
    logger.info("POST /entities committed portfolio_entity id=%s user_id=%s", e.id, current_user.id)
    db.refresh(e)
    if inst_id:
        logger.info(
            "bind_instrument bind_success context=create_entity entity_id=%s instrument_id=%s",
            e.id,
            inst_id,
        )
    if warm_symbol:
        schedule_market_snapshot_refresh_for_symbols([warm_symbol])
    return _entity_out(e)


@router.patch("/entities/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: str,
    payload: EntityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityOut:
    eid = uuid.UUID(entity_id)
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    warm_symbol: str | None = None
    if payload.name is not None:
        e.name = payload.name
    patch = payload.model_dump(exclude_unset=True)
    if "instrument_id" in patch or "instrument_resolve" in patch:
        if (
            "instrument_id" in patch
            and patch["instrument_id"] is None
            and not payload.instrument_resolve
        ):
            e.instrument_id = None
            logger.info("bind_instrument bind_success context=update_entity action=clear entity_id=%s", eid)
        else:
            try:
                resolved = _resolve_instrument_id_for_bind(
                    db,
                    instrument_id=payload.instrument_id,
                    resolve=payload.instrument_resolve,
                    log_context="update_entity",
                )
            except HTTPException:
                logger.warning("bind_instrument bind_failed context=update_entity (HTTP error)")
                raise
            e.instrument_id = resolved
            if e.instrument_id:
                inst = db.get(Instrument, e.instrument_id)
                if inst and inst.symbol:
                    register_instrument_quote_subscription(db, current_user.id, inst.symbol.strip())
                    warm_symbol = inst.symbol.strip()
                logger.info(
                    "bind_instrument bind_success context=update_entity entity_id=%s instrument_id=%s",
                    eid,
                    e.instrument_id,
                )
    if payload.chart_layout is not None:
        e.chart_layout = _normalize_chart_layout(dict(payload.chart_layout))
        flag_modified(e, "chart_layout")
    upsert_target_entity_for_portfolio_entity(db, e, name=e.name)
    db.commit()
    logger.info("PATCH /entities committed id=%s user_id=%s", e.id, current_user.id)
    db.refresh(e)
    if warm_symbol:
        schedule_market_snapshot_refresh_for_symbols([warm_symbol])
    return _entity_out(e)


@router.delete("/entities/{entity_id}", status_code=status.HTTP_200_OK)
def delete_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    eid = uuid.UUID(entity_id)
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    # Remove loose JSON references in research layouts to prevent orphan UI pointers.
    refs_removed = remove_entity_from_research_layouts(db, current_user.id, eid)
    # Remove entity-scoped subscriptions so worker will not enqueue updates for deleted entity.
    subs_removed = remove_entity_subscriptions(db, current_user.id, eid)
    # Explicit metric cleanup (even though FK cascade handles it) for deterministic lifecycle behavior.
    metrics_deleted = db.execute(delete(EntityDailyMetric).where(EntityDailyMetric.entity_id == eid)).rowcount or 0
    delete_target_entity_record(db, eid)
    db.delete(e)
    db.commit()
    logger.info(
        "DELETE /entities committed id=%s user_id=%s subscriptions_removed=%d metrics_deleted=%d research_refs_removed=%d",
        eid,
        current_user.id,
        subs_removed,
        metrics_deleted,
        refs_removed,
    )


@router.get("/entities/{entity_id}/terms", response_model=list[TermOut])
def list_terms(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TermOut]:
    eid = uuid.UUID(entity_id)
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    return [TermOut(id=str(t.id), term=t.term, normalized_term=t.normalized_term, created_at=t.created_at) for t in e.terms]


@router.post("/entities/{entity_id}/terms", response_model=TermOut, status_code=status.HTTP_201_CREATED)
def add_term(
    entity_id: str,
    payload: TermCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TermOut:
    eid = uuid.UUID(entity_id)
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if len(e.terms) >= MAX_TERMS:
        raise HTTPException(status_code=400, detail=f"Max {MAX_TERMS} terms per entity")
    norm = _norm(payload.term)
    if not norm:
        raise HTTPException(status_code=400, detail="Term cannot be empty")
    for t in e.terms:
        if t.normalized_term == norm:
            raise HTTPException(status_code=400, detail="Term already exists")
    t = EntityTerm(entity_id=eid, term=payload.term.strip(), normalized_term=norm)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TermOut(id=str(t.id), term=t.term, normalized_term=t.normalized_term, created_at=t.created_at)


@router.put("/entities/{entity_id}/terms", response_model=list[TermOut])
def replace_terms(
    entity_id: str,
    payload: TermsReplace,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TermOut]:
    eid = uuid.UUID(entity_id)
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    for t in e.terms:
        db.delete(t)
    db.flush()
    for norm in _sanitize(payload.terms or []):
        db.add(EntityTerm(entity_id=eid, term=norm, normalized_term=norm))
    rows_synced = 0
    if payload.terms:
        rows_synced = sync_entity_search_trend(db, eid, timeframe="today 3-m")
    db.commit()
    logger.info("entity terms replaced entity_id=%s terms=%d metrics_synced=%d", eid, len(payload.terms or []), rows_synced)
    db.refresh(e)
    terms = db.scalars(select(EntityTerm).where(EntityTerm.entity_id == eid)).all()
    return [TermOut(id=str(t.id), term=t.term, normalized_term=t.normalized_term, created_at=t.created_at) for t in terms]


@router.delete("/terms/{term_id}", status_code=status.HTTP_200_OK)
def delete_term(
    term_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    tid = uuid.UUID(term_id)
    t = db.scalar(select(EntityTerm).where(EntityTerm.id == tid))
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    e = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == t.entity_id, PortfolioEntity.user_id == current_user.id))
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(t)
    db.commit()


@router.get("/entities/{entity_id}/related-instruments", response_model=list[RelatedInstrumentOut])
def list_related_instruments(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RelatedInstrumentOut]:
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(selectinload(PortfolioEntity.related_instruments).selectinload(EntityRelatedInstrument.instrument))
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return [
        RelatedInstrumentOut(
            id=str(ri.id),
            instrument_id=str(ri.instrument_id),
            symbol=ri.instrument.symbol,
            display_name=ri.instrument.display_name,
            asset_class=ri.instrument.asset_class,
        )
        for ri in sorted(entity.related_instruments, key=lambda x: (x.display_order, x.created_at))
    ]


@router.post("/entities/{entity_id}/related-instruments", response_model=RelatedInstrumentOut, status_code=status.HTTP_201_CREATED)
def add_related_instrument(
    entity_id: str,
    payload: AddRelatedInstrumentBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RelatedInstrumentOut:
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(selectinload(PortfolioEntity.related_instruments))
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    if len(entity.related_instruments) >= MAX_ITEMS_PER_ENTITY:
        raise HTTPException(status_code=400, detail=MSG_MAX_ITEMS_PER_ENTITY)
    try:
        inst_id = _resolve_instrument_id_for_bind(
            db,
            instrument_id=payload.instrument_id,
            resolve=payload.instrument_resolve,
            log_context="add_related_instrument",
        )
    except HTTPException:
        logger.warning("bind_instrument bind_failed context=add_related_instrument (HTTP error)")
        raise
    if inst_id is None:
        logger.warning("bind_instrument bind_failed context=add_related_instrument reason=no_instrument_id")
        raise HTTPException(status_code=400, detail="instrument_id required")
    inst = db.scalar(select(Instrument).where(Instrument.id == inst_id, Instrument.is_active.is_(True)))
    if not inst:
        raise HTTPException(status_code=404, detail="Instrument not found")
    for ri in entity.related_instruments:
        if ri.instrument_id == inst_id:
            raise HTTPException(status_code=400, detail="Instrument already added as related")
    display_order = max((ri.display_order for ri in entity.related_instruments), default=-1) + 1
    ri = EntityRelatedInstrument(entity_id=eid, instrument_id=inst_id, display_order=display_order)
    db.add(ri)
    warm_symbol = inst.symbol.strip() if inst.symbol else None
    if warm_symbol:
        register_instrument_quote_subscription(db, current_user.id, warm_symbol)
        try:
            from app.services.active_market_pool_service import record_active_pool_interaction

            record_active_pool_interaction(db, warm_symbol)
        except Exception:
            logger.warning("active_pool record failed symbol=%s", warm_symbol, exc_info=True)
    db.commit()
    db.refresh(ri)
    logger.info(
        "bind_instrument bind_success context=add_related_instrument entity_id=%s instrument_id=%s related_row_id=%s",
        eid,
        inst_id,
        ri.id,
    )
    if warm_symbol:
        schedule_market_snapshot_refresh_for_symbols([warm_symbol])
    return RelatedInstrumentOut(
        id=str(ri.id),
        instrument_id=str(ri.instrument_id),
        symbol=ri.instrument.symbol,
        display_name=ri.instrument.display_name,
        asset_class=ri.instrument.asset_class,
    )


@router.delete("/entities/{entity_id}/related-instruments/{related_id}", status_code=status.HTTP_200_OK)
def delete_related_instrument(
    entity_id: str,
    related_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    eid = uuid.UUID(entity_id)
    rid = uuid.UUID(related_id)
    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    ri = db.scalar(
        select(EntityRelatedInstrument).where(
            EntityRelatedInstrument.id == rid,
            EntityRelatedInstrument.entity_id == eid,
        )
    )
    if not ri:
        raise HTTPException(status_code=404, detail="Related instrument not found")
    db.delete(ri)
    db.commit()


@router.get("/entities/{entity_id}/comparison-series", response_model=ComparisonSeriesOut)
def get_comparison_series(
    entity_id: str,
    instrument_ids: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonSeriesOut:
    """Return normalized OHLCV series from DB snapshots only (each line starts at 100)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    raw_ids = [x.strip() for x in instrument_ids.split(",") if x.strip()][:MAX_COMPARISON_INSTRUMENTS]
    if not raw_ids:
        raise HTTPException(status_code=400, detail="At least one instrument_id required")
    ids = []
    for s in raw_ids:
        try:
            ids.append(uuid.UUID(s))
        except ValueError:
            continue
    instruments = db.scalars(select(Instrument).where(Instrument.id.in_(ids))).all()
    by_id = {i.id: i for i in instruments}
    from datetime import timezone

    series_lines: list[ComparisonSeriesLine] = []
    all_bars: list[tuple[uuid.UUID, str, list[dict]]] = []
    latest_snap: datetime | None = None
    batch_stale = False
    for iid in ids:
        inst = by_id.get(iid)
        if not inst:
            continue
        snap = db.get(OhlcvSnapshot, f"{inst.symbol.upper()}:{period.upper()}")
        if snap:
            if snap.is_stale:
                batch_stale = True
            if snap.last_success_at and (latest_snap is None or snap.last_success_at > latest_snap):
                latest_snap = snap.last_success_at
        bars = ((snap.bars or {}).get("bars", []) if snap and snap.bars else [])
        if bars:
            all_bars.append((iid, inst.symbol, bars))
    if not all_bars:
        return ComparisonSeriesOut(
            period=period,
            series=[],
            data_updated_at=None,
            data_source="stale_fallback",
            stale=True,
        )
    # Align dates: use union of all timestamps, then for each instrument forward-fill and normalize to 100
    dates_sorted: list[datetime] = sorted(
        {
            datetime.fromtimestamp(int(b.get("time")), tz=timezone.utc)
            for _, _, bars in all_bars
            for b in bars
            if b.get("time") is not None
        }
    )
    if not dates_sorted:
        lu_empty = latest_snap.isoformat() if latest_snap else None
        return ComparisonSeriesOut(
            period=period,
            series=[],
            data_updated_at=lu_empty,
            data_source="stale_fallback" if batch_stale else "snapshot",
            stale=batch_stale,
        )
    by_date: dict[tuple[uuid.UUID, str], dict[datetime, float]] = {}
    for iid, symbol, bars in all_bars:
        by_date[(iid, symbol)] = {
            datetime.fromtimestamp(int(b.get("time")), tz=timezone.utc): (
                float(b.get("close")) if b.get("close") is not None else float(b.get("open") or 0)
            )
            for b in bars
            if b.get("time") is not None
        }
    base_date = dates_sorted[0]
    for iid, symbol, bars in all_bars:
        closes = [by_date[(iid, symbol)].get(d) for d in dates_sorted]
        # Forward-fill missing
        last = None
        for i in range(len(closes)):
            if closes[i] is not None:
                last = closes[i]
            elif last is not None:
                closes[i] = last
        if not closes or closes[0] is None or closes[0] == 0:
            continue
        base_val = float(closes[0])
        points = [
            ComparisonSeriesPoint(t=d.isoformat(), value=round((float(c or 0) / base_val) * 100, 2))
            for d, c in zip(dates_sorted, closes)
            if c is not None
        ]
        series_lines.append(ComparisonSeriesLine(instrument_id=str(iid), symbol=symbol, points=points))
    lu_iso = latest_snap.isoformat() if latest_snap else None
    record_snapshot_hit("entity_comparison_series")
    return ComparisonSeriesOut(
        period=period,
        series=series_lines,
        data_updated_at=lu_iso,
        data_source="stale_fallback" if batch_stale else "snapshot",
        stale=batch_stale,
    )


# Period to approximate number of days for analytics time series (aligned with market PERIOD_TO_DAYS)
_ANALYTICS_PERIOD_DAYS: dict[str, int | None] = {
    "1D": 7,
    "5D": 10,
    "1M": 35,
    "6M": 200,
    "1Y": 400,
    "MAX": 500,
}


def _mock_search_volume_series(terms: list[str], period: str) -> list[TimeSeriesPoint]:
    """Deterministic mock search volume from entity terms. Uses term string + date seed for reproducibility."""
    from datetime import datetime, timezone, timedelta

    days = _ANALYTICS_PERIOD_DAYS.get(period, 35) or 35
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    base = sum(ord(c) for c in seed) % 50 + 60  # 60–110 base
    points: list[TimeSeriesPoint] = []
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days, -1, -1):
        d = now - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        h = hash((seed, day_str, "search")) % 100
        value = base + (h % 40) - 10  # vary around base
        points.append(TimeSeriesPoint(t=day_str, value=round(float(max(1, value)), 2)))
    return points


def _mock_coverage_volume_series(terms: list[str], period: str) -> list[TimeSeriesPoint]:
    """Deterministic mock coverage volume from entity terms. Different seed than search for variety."""
    from datetime import datetime, timezone, timedelta

    days = _ANALYTICS_PERIOD_DAYS.get(period, 35) or 35
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    base = sum(ord(c) for c in seed) % 30 + 40  # 40–70 base
    points: list[TimeSeriesPoint] = []
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days, -1, -1):
        d = now - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        h = hash((seed, day_str, "coverage")) % 100
        value = base + (h % 35) - 5
        points.append(TimeSeriesPoint(t=day_str, value=round(float(max(1, value)), 2)))
    return points


def _mock_sentiment_series(terms: list[str], period: str) -> list[TimeSeriesPoint]:
    """Deterministic mock sentiment time series from entity terms (-1 to 1 scale)."""
    from datetime import datetime, timezone, timedelta

    days = _ANALYTICS_PERIOD_DAYS.get(period, 35) or 35
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    points: list[TimeSeriesPoint] = []
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days, -1, -1):
        d = now - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        h = hash((seed, day_str, "sentiment")) % 200  # 0..199
        value = (h - 100) / 100.0  # -1.0 to 0.99
        points.append(TimeSeriesPoint(t=day_str, value=round(float(value), 3)))
    return points


# Period to days for narrative flow / quadrant history (aligned with analysis periods)
_QUADRANT_HISTORY_DAYS: dict[str, int] = {
    "7D": 7,
    "1M": 35,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "MAX": 500,
}


def _mock_quadrant_history(terms: list[str], period: str) -> list[QuadrantHistoryPoint]:
    """Smooth deterministic walk: base point from terms, then small bounded deltas per day. Clamp to [-50, 50]."""
    from datetime import datetime, timezone, timedelta

    days = _QUADRANT_HISTORY_DAYS.get(period.strip().upper(), 35)
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    base_s = (hash((seed, "base_s")) % 60) - 30
    base_c = (hash((seed, "base_c")) % 60) - 30
    points: list[QuadrantHistoryPoint] = []
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sm, cm = float(base_s), float(base_c)
    for i in range(days, -1, -1):
        d = now - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        h = hash((seed, day_str, "qh_walk"))
        delta_s = ((h % 21) - 10) * 0.8
        delta_c = ((h // 21) % 21 - 10) * 0.8
        sm = max(-50, min(50, sm + delta_s))
        cm = max(-50, min(50, cm + delta_c))
        points.append(
            QuadrantHistoryPoint(
                t=day_str,
                coverage_volume=max(0.0, min(100.0, 50.0 + cm)),
                keywords_search_volume=max(0.0, min(500.0, 50.0 + sm)),
            )
        )
    period_upper = period.strip().upper()
    if period_upper == "1M" and len(points) > 15:
        sampled = [points[i] for i in range(0, len(points), 2)]
        if sampled and sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        points = sampled
    elif period_upper in ("3M", "6M") and len(points) > 20:
        step = max(1, len(points) // 18)
        sampled = [points[i] for i in range(0, len(points), step)]
        if sampled and sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        points = sampled
    elif period_upper in ("1Y", "MAX") and len(points) > 24:
        step = max(1, len(points) // 24)
        sampled = [points[i] for i in range(0, len(points), step)]
        if sampled and sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        points = sampled
    return points


def _mock_quadrant(terms: list[str]) -> QuadrantOut:
    """Unused mock scaffold (deterministic scalars)."""
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    k = float((hash((seed, "k")) % 101))
    c = float((hash((seed, "c")) % 101))
    return QuadrantOut(
        keywords_search_volume=k,
        coverage_volume=c,
        last_updated_at=None,
        stale=True,
        data_updated_at=None,
        data_source="stale_fallback",
        loading_state="stale",
        message=None,
    )


def _mock_sentiment_change(terms: list[str]) -> float:
    """Single scalar sentiment change for trending (mock). E.g. -50 to 50."""
    seed = "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"
    return float((hash((seed, "sentiment_change")) % 101) - 50)


@router.get("/entities/{entity_id}/search-volume-series", response_model=TimeSeriesOut)
def get_search_volume_series(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeSeriesOut:
    """Deprecated alias: narrative keywords search volume (same as /keywords-search-volume-series)."""
    return get_keywords_search_volume_series(entity_id, period, db, current_user)


@router.get("/entities/{entity_id}/keywords-search-volume-series", response_model=TimeSeriesOut)
def get_keywords_search_volume_series(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeSeriesOut:
    """Time series: sum of independent narrative-keyword Google Trends indices (per day)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms),
            selectinload(PortfolioEntity.instrument),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    raw_pts, _last_any, _stale_pts = entity_metric_timeseries_bundle(db, entity.id, "keywords_search_volume", period)
    points = [TimeSeriesPoint(t=p["t"], value=p["value"]) for p in raw_pts]
    tgt, narr = entity_target_and_narrative_keywords(entity)
    last_st = last_keywords_search_success_at(db, entity.id)
    stale = len(points) == 0
    if stale:
        sig = {
            "last_updated_at": last_st.isoformat() if last_st else None,
            "data_updated_at": last_st.isoformat() if last_st else None,
            "data_source": "unavailable",
            "loading_state": "no_data",
            "message": explain_search_volumes_absence(db, entity.id, has_target=bool(tgt), has_narrative_terms=bool(narr)),
            "stale": True,
        }
    else:
        sig = _entity_signal_envelope(last_st, False)
    record_snapshot_hit("entity_keywords_search_volume_series")
    record_first_paint_envelope(
        "entity_keywords_search_volume_series",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return TimeSeriesOut(period=period, points=points, data=points, **sig)


@router.get("/entities/{entity_id}/target-search-volume-series", response_model=TimeSeriesOut)
def get_target_search_volume_series(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeSeriesOut:
    """Time series: primary instrument symbol Google Trends index (ticker / target intent)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms),
            selectinload(PortfolioEntity.instrument),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    raw_pts, _last_any, _stale_pts = entity_metric_timeseries_bundle(db, entity.id, "target_search_volume", period)
    points = [TimeSeriesPoint(t=p["t"], value=p["value"]) for p in raw_pts]
    tgt, narr = entity_target_and_narrative_keywords(entity)
    last_tt = last_target_search_success_at(db, entity.id)
    stale = len(points) == 0
    if stale:
        msg = (
            "Link a primary instrument to load target (ticker) search volume."
            if not tgt
            else explain_search_volumes_absence(db, entity.id, has_target=True, has_narrative_terms=bool(narr))
        )
        sig = {
            "last_updated_at": last_tt.isoformat() if last_tt else None,
            "data_updated_at": last_tt.isoformat() if last_tt else None,
            "data_source": "unavailable",
            "loading_state": "no_data",
            "message": msg,
            "stale": True,
        }
    else:
        sig = _entity_signal_envelope(last_tt, False)
    record_snapshot_hit("entity_target_search_volume_series")
    record_first_paint_envelope(
        "entity_target_search_volume_series",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return TimeSeriesOut(period=period, points=points, data=points, **sig)


@router.get("/entities/{entity_id}/coverage-volume-series", response_model=TimeSeriesOut)
def get_coverage_volume_series(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeSeriesOut:
    """Time series of coverage_volume from DB snapshots only."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    raw_pts, last, stale = entity_metric_timeseries_bundle(db, entity.id, "coverage_volume", period)
    points = [TimeSeriesPoint(t=p["t"], value=p["value"]) for p in raw_pts]
    sig = _entity_signal_envelope(last, stale)
    record_snapshot_hit("entity_coverage_volume_series")
    record_first_paint_envelope(
        "entity_coverage_volume_series",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return TimeSeriesOut(period=period, points=points, data=points, **sig)


@router.get("/entities/{entity_id}/triple-signal-series", response_model=TripleSignalSeriesOut)
def get_triple_signal_series(
    entity_id: str,
    period: str = "3M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TripleSignalSeriesOut:
    """DB-backed normalized triple signal lines (trading/news/search), no provider calls in request path."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    p = (period or "3M").strip().upper()
    days = 30 if p in {"1M", "30D"} else 180 if p in {"6M", "1Y", "MAX"} else 90
    payload = read_entity_triple_signal_series_aligned(db, entity.id, period_days=days)
    axis = list(payload.get("axis") or [])
    trading = list(payload.get("trading_activity") or [])
    news = list(payload.get("news_volume") or [])
    search = list(payload.get("search_volume") or [])
    last_updated = payload.get("last_updated_at")
    stale = not any(v is not None for v in trading + news + search)
    return TripleSignalSeriesOut(
        period=p,
        axis=axis,
        trading_activity=trading,
        news_volume=news,
        search_volume=search,
        last_updated_at=last_updated,
        data_updated_at=last_updated,
        stale=stale,
        data_source="snapshot" if not stale else "unavailable",
    )


@router.get("/entities/{entity_id}/sentiment-series", response_model=SentimentSeriesOut)
def get_sentiment_series(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SentimentSeriesOut:
    """
    AI-backed sentiment series from normalized news:
    - Uses normalized_news_documents as corpus
    - Compares each bucket vs prior equal-length baseline window (delta sentiment)
    Gating:
    - Admin-only today (feature tiers)
    - Runtime-flagged (ENABLE_AI_FEATURES + ENABLE_AI_NEWS_SUMMARY)
    """
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Feature tier gate (admin-only today). Return an honest 200 w/ empty points (not fake).
    if not can_access_feature(current_user, FeatureKey.ENTITY_SENTIMENT_AI):
        return SentimentSeriesOut(
            period=period,
            points=[],
            data=[],
            last_updated_at=None,
            data_updated_at=None,
            stale=True,
            data_source="disabled",
            loading_state="disabled",
            message="AI sentiment requires a plan with AI access.",
            eta_hint=None,
        )

    # Runtime flags: do not call any provider when disabled.
    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_NEWS_SUMMARY):
        return SentimentSeriesOut(
            period=period,
            points=[],
            data=[],
            last_updated_at=None,
            data_updated_at=None,
            stale=True,
            data_source="disabled_by_runtime_flag",
            loading_state="disabled",
            message="AI sentiment series is disabled by runtime flag.",
            eta_hint=None,
        )

    # Clamp >1Y requests to 1Y to cap AI cost.
    p_norm = str((period or "1M").strip().upper())
    if p_norm not in {"1M", "3M", "6M", "1Y", "MAX"}:
        p_norm = "3M"
    if p_norm == "MAX":
        p_norm = "1Y"

    # Non-blocking behavior: return cached buckets immediately; compute missing in background.
    cached_pts, missing_count, baseline_cached, _step = read_cached_sentiment_series(db, entity_id=entity.id, period=p_norm)
    out_pts = [
        SentimentSeriesPoint(
            t=p.t,
            sentiment_score=float(p.sentiment_score),
            sentiment_label=p.sentiment_label,
            confidence=p.confidence,
        )
        for p in cached_pts
    ]

    eta_hint = "≈1–3s" if p_norm in {"1M", "3M"} else "≈3–10s"
    now_iso = datetime.now(timezone.utc).isoformat()

    # If anything missing, enqueue background compute (best-effort) and return partial/computing state.
    if missing_count > 0 or not baseline_cached:
        try:
            from app.worker.celery_app import celery_app

            celery_app.send_task(
                "app.worker.tasks.compute_entity_sentiment_series",
                args=[str(entity.id), p_norm],
            )
        except Exception:
            logger.warning("sentiment-series enqueue failed entity_id=%s", entity.id, exc_info=True)

        state = "computing" if len(out_pts) == 0 else "partial"
        return SentimentSeriesOut(
            period=p_norm,
            points=out_pts,
            data=out_pts,
            last_updated_at=now_iso,
            data_updated_at=now_iso,
            stale=False,
            data_source="ai_news_delta_cache",
            loading_state=state,
            message="Computing (AI)..." if state == "computing" else "Updating…",
            eta_hint=eta_hint,
        )

    record_snapshot_hit("entity_sentiment_series_ai")
    return SentimentSeriesOut(
        period=p_norm,
        points=out_pts,
        data=out_pts,
        last_updated_at=now_iso,
        data_updated_at=now_iso,
        stale=False,
        data_source="ai_news_delta_cache",
        loading_state="complete",
        message=None,
        eta_hint=eta_hint,
    )


@router.get("/entities/{entity_id}/quadrant", response_model=QuadrantOut)
def get_quadrant(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuadrantOut:
    """Current quadrant: keywords_search_volume (y) and coverage_volume (x)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    sv, cv, last, stale = entity_quadrant_current_bundle(db, entity.id)
    sig = _entity_signal_envelope(last, stale)
    record_snapshot_hit("entity_quadrant")
    record_first_paint_envelope(
        "entity_quadrant",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return QuadrantOut(keywords_search_volume=sv, coverage_volume=cv, **sig)


@router.get("/entities/{entity_id}/quadrant-history", response_model=QuadrantHistoryOut)
def get_quadrant_history(
    entity_id: str,
    period: str = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuadrantHistoryOut:
    """Time series of quadrant flow from DB snapshots only."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    period_upper = (period.strip().upper() or "1M")
    raw_pts, last, stale = entity_quadrant_history_bundle(db, entity.id, period)
    points = [
        QuadrantHistoryPoint(
            t=p["t"],
            coverage_volume=p["coverage_volume"],
            keywords_search_volume=p["keywords_search_volume"],
        )
        for p in raw_pts
    ]
    sig = _entity_signal_envelope(last, stale)
    record_snapshot_hit("entity_quadrant_history")
    record_first_paint_envelope(
        "entity_quadrant_history",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return QuadrantHistoryOut(period=period_upper, points=points, data=points, **sig)


@router.get("/entities/{entity_id}/trending", response_model=TrendingOut)
def get_trending(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrendingOut:
    """Neutral analytics summary from DB snapshots only."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    search_m, coverage_m, sentiment_change, trend_label, last, stale = entity_trending_bundle(db, entity.id)
    sig = _entity_signal_envelope(last, stale)
    record_snapshot_hit("entity_trending")
    record_first_paint_envelope(
        "entity_trending",
        loading_state=str(sig["loading_state"]),
        data_source=str(sig["data_source"]),
    )
    return TrendingOut(
        search_momentum=search_m,
        coverage_momentum=coverage_m,
        sentiment_change=sentiment_change,
        trend_label=trend_label,
        **sig,
    )


def _clamp100(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


@router.get("/entities/{entity_id}/analysis/institution-bias", response_model=InstitutionBiasOut)
def get_institution_bias(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InstitutionBiasOut:
    """
    DB-only heuristic proxy for 'institution bias' (no external APIs, no AI).
    Uses stored momentum/coverage/sentiment deltas as a directional signal only.
    """
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    search_m, coverage_m, sentiment_change, _trend_label, last, stale = entity_trending_bundle(db, entity.id)
    sig = _entity_signal_envelope(last, stale)

    score = 50.0 + (0.6 * float(search_m)) + (0.6 * float(coverage_m)) + (0.2 * float(sentiment_change))
    score = _clamp100(score)
    if score >= 60:
        bias = "Bullish"
    elif score <= 40:
        bias = "Bearish"
    else:
        bias = "Neutral"

    bullish = _clamp100((score - 50.0) * 2.0)
    bearish = _clamp100((50.0 - score) * 2.0)
    neutral = _clamp100(100.0 - max(bullish, bearish))

    lu = sig.get("last_updated_at")
    return InstitutionBiasOut(
        bias_label=bias,
        score=round(score, 2),
        bullish_pct=round(bullish, 2),
        neutral_pct=round(neutral, 2),
        bearish_pct=round(bearish, 2),
        last_updated_at=lu,
        data_updated_at=lu,
        **sig,
    )


@router.get("/entities/{entity_id}/analysis/rating-distribution", response_model=RatingDistributionOut)
def get_rating_distribution(
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RatingDistributionOut:
    """
    DB-only heuristic proxy for rating distribution (buy/hold/sell).
    This is NOT analyst coverage; it is derived from stored narrative metrics only.
    """
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    search_m, coverage_m, sentiment_change, _trend_label, last, stale = entity_trending_bundle(db, entity.id)
    sig = _entity_signal_envelope(last, stale)

    score = 50.0 + (0.6 * float(search_m)) + (0.6 * float(coverage_m)) + (0.2 * float(sentiment_change))
    score = _clamp100(score)
    buy = _clamp100(max(0.0, score - 50.0) * 2.0)
    sell = _clamp100(max(0.0, 50.0 - score) * 2.0)
    hold = _clamp100(100.0 - buy - sell)

    conf = 20.0 if stale else 65.0
    conf += min(25.0, (abs(float(search_m)) + abs(float(coverage_m))) * 0.2)
    conf = _clamp100(conf)

    lu = sig.get("last_updated_at")
    return RatingDistributionOut(
        buy_pct=round(buy, 2),
        hold_pct=round(hold, 2),
        sell_pct=round(sell, 2),
        confidence=round(conf, 2),
        last_updated_at=lu,
        data_updated_at=lu,
        **sig,
    )


@router.get("/entities/{entity_id}/charts/3d-data", response_model=EntityChart3DDataOut)
def get_entity_chart_3d_data(
    entity_id: str,
    chart_range: str = Query("1m", alias="range", description="1m | 3m | 6m"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityChart3DDataOut:
    """
    Time × keywords_search_volume × coverage_volume: narrative Trends aggregate + real coverage (per day).
    """
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms)
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rk = normalize_chart_3d_range(chart_range)
    raw, src_status = get_chart_3d_payload(db, entity.id, rk)
    points = [
        Chart3DPoint(
            date=str(r["date"]),
            keywords_search_volume=float(r["keywords_search_volume"]),
            coverage_volume=float(r["coverage_volume"]),
        )
        for r in raw
    ]
    last_st = last_keywords_search_success_at(db, entity.id)
    lu = last_st.isoformat() if last_st else None
    st = len(points) == 0
    terms = [t.term for t in entity.terms]
    msg = explain_chart_3d_absence(db, entity.id, terms, src_status) if st else None
    record_snapshot_hit("entity_chart_3d")
    return EntityChart3DDataOut(
        entity_id=str(entity.id),
        range=rk,
        mode="search_vs_coverage",
        points=points,
        data=points,
        last_updated_at=lu,
        stale=st,
        source_status=Chart3DSourceStatus(
            keywords_search_volume=src_status["keywords_search_volume"],
            coverage_volume=src_status["coverage_volume"],
            target_search_volume="n/a",
        ),
        data_updated_at=lu,
        data_source="unavailable" if st else "snapshot",
        message=msg,
    )


@router.get("/entities/{entity_id}/metrics/search-trend", response_model=EntityKeywordsSearchSeriesOut)
def get_entity_search_trend_series(
    entity_id: str,
    chart_range: str = Query("1m", alias="range", description="1m | 3m | 6m"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityKeywordsSearchSeriesOut:
    """Deprecated path name: narrative keywords search volume (not target/ticker)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms),
            selectinload(PortfolioEntity.instrument),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    tgt, narr = entity_target_and_narrative_keywords(entity)
    rk = normalize_chart_3d_range(chart_range)
    raw, src = get_entity_keywords_search_timeseries(db, entity.id, rk)
    points = [KeywordsSearchPoint(date=str(r["date"]), keywords_search_volume=float(r["keywords_search_volume"])) for r in raw]
    last_st = last_keywords_search_success_at(db, entity.id)
    lu = last_st.isoformat() if last_st else None
    st = len(points) == 0
    msg = explain_search_volumes_absence(db, entity.id, has_target=bool(tgt), has_narrative_terms=bool(narr)) if st else None
    record_snapshot_hit("entity_keywords_search_series")
    return EntityKeywordsSearchSeriesOut(
        entity_id=str(entity.id),
        range=rk,
        points=points,
        data=points,
        last_updated_at=lu,
        stale=st,
        source_status=Chart3DSourceStatus(
            keywords_search_volume=src.get("keywords_search_volume", "unavailable"),
            coverage_volume="n/a",
            target_search_volume="n/a",
        ),
        data_updated_at=lu,
        data_source="unavailable" if st else "snapshot",
        message=msg,
    )


@router.get("/entities/{entity_id}/metrics/keywords-search-volume", response_model=EntityKeywordsSearchSeriesOut)
def get_entity_keywords_search_series(
    entity_id: str,
    chart_range: str = Query("1m", alias="range", description="1m | 3m | 6m"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityKeywordsSearchSeriesOut:
    return get_entity_search_trend_series(entity_id, chart_range, db, current_user)


@router.get("/entities/{entity_id}/metrics/target-search-volume", response_model=EntityTargetSearchSeriesOut)
def get_entity_target_search_series(
    entity_id: str,
    chart_range: str = Query("1m", alias="range", description="1m | 3m | 6m"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EntityTargetSearchSeriesOut:
    """Primary instrument symbol Trends index (per day)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id).options(
            selectinload(PortfolioEntity.terms),
            selectinload(PortfolioEntity.instrument),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    tgt, narr = entity_target_and_narrative_keywords(entity)
    rk = normalize_chart_3d_range(chart_range)
    raw, src = get_entity_target_search_timeseries(db, entity.id, rk)
    points = [TargetSearchPoint(date=str(r["date"]), target_search_volume=float(r["target_search_volume"])) for r in raw]
    last_tt = last_target_search_success_at(db, entity.id)
    lu = last_tt.isoformat() if last_tt else None
    st = len(points) == 0
    msg = (
        "Link a primary instrument to load target search volume."
        if st and not tgt
        else explain_search_volumes_absence(db, entity.id, has_target=bool(tgt), has_narrative_terms=bool(narr))
        if st
        else None
    )
    record_snapshot_hit("entity_target_search_series")
    return EntityTargetSearchSeriesOut(
        entity_id=str(entity.id),
        range=rk,
        points=points,
        data=points,
        last_updated_at=lu,
        stale=st,
        source_status=Chart3DSourceStatus(
            keywords_search_volume="n/a",
            coverage_volume="n/a",
            target_search_volume=src.get("target_search_volume", "unavailable"),
        ),
        data_updated_at=lu,
        data_source="unavailable" if st else "snapshot",
        message=msg,
    )


@router.get("/entities/{entity_id}/price-timeline/points", response_model=TimelinePointsResponse)
def get_entity_price_timeline_points(
    entity_id: str,
    symbol: str = Query(..., min_length=1, max_length=32),
    period: str = Query("1M", max_length=8),
    chart_scope: str = Query("main", max_length=32, description="main | compare | workspace label"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelinePointsResponse:
    """Timeline markers under price charts: volatility + important news points."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(
            selectinload(PortfolioEntity.instrument),
            selectinload(PortfolioEntity.related_instruments).selectinload(EntityRelatedInstrument.instrument),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return build_timeline_points(
        db,
        user=current_user,
        symbol=symbol,
        period=period,
        chart_scope=(chart_scope or "main").strip() or "main",
    )


@router.get("/entities/{entity_id}/price-timeline/window", response_model=TimelineWindowResponse)
def get_entity_price_timeline_window(
    entity_id: str,
    point_id: str = Query(..., min_length=3, max_length=256),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineWindowResponse:
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(selectinload(PortfolioEntity.instrument), selectinload(PortfolioEntity.terms))
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    terms = [t.term for t in entity.terms]
    win = get_timeline_window(
        db=db,
        _user=current_user,
        entity=entity,
        point_id=point_id,
        entity_terms=terms,
    )
    if not win:
        raise HTTPException(status_code=400, detail="Invalid timeline point")
    return win


@router.post("/entities/{entity_id}/price-timeline/ai-summary", response_model=AiSummaryResponse)
def post_entity_price_timeline_ai_summary(
    entity_id: str,
    body: AiSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature(FeatureKey.TIMELINE_AI_SUMMARY)),
) -> AiSummaryResponse:
    from app.services.runtime_flags import RuntimeFlagKey, ai_feature_enabled

    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_TIMELINE_SUMMARY):
        return AiSummaryResponse(
            status="placeholder",
            provider=body.provider,
            interpretation=None,
            summary="AI timeline summary is temporarily disabled.",
            citations=[],
            model_label=None,
            detail="disabled_by_runtime_flag",
        )
    eid = uuid.UUID(entity_id)
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id)
        .options(
            selectinload(PortfolioEntity.instrument),
            selectinload(PortfolioEntity.terms),
        )
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    term_strs = [t.term for t in entity.terms]
    win = get_timeline_window(
        db=db,
        _user=current_user,
        entity=entity,
        point_id=body.point_id,
        entity_terms=term_strs,
    )
    if not win:
        raise HTTPException(status_code=400, detail="Invalid timeline point")
    return ai_summary_placeholder(
        provider=body.provider,
        point_id=body.point_id,
        window=win,
        summary_window=body.summary_window,
        custom_start_iso=body.custom_start_iso,
        custom_end_iso=body.custom_end_iso,
    )


@router.get("/entities/{entity_id}/news-documents")
def get_entity_news_documents(
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Read normalized entity news from DB only (no external fetch in GET)."""
    eid = uuid.UUID(entity_id)
    entity = db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == eid, PortfolioEntity.user_id == current_user.id))
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rows = db.scalars(
        select(NormalizedNewsDocument)
        .where(NormalizedNewsDocument.entity_id == entity.id)
        .order_by(NormalizedNewsDocument.published_at.desc().nullslast(), NormalizedNewsDocument.created_at.desc())
        .limit(limit)
    ).all()
    data = [
        {
            "id": str(r.id),
            "canonical_url": r.canonical_url,
            "normalized_title": r.normalized_title,
            "source_channel": r.source_channel,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "dedup_cluster_id": str(r.dedup_cluster_id) if r.dedup_cluster_id else None,
        }
        for r in rows
    ]
    last_updated_at = None
    if rows:
        ts = rows[0].published_at or rows[0].created_at
        last_updated_at = ts.isoformat() if ts else None
    return {"data": data, "last_updated_at": last_updated_at, "stale": len(data) == 0}


# Category filter: All | Stock | ETF | Index | Futures | Crypto | Hong Kong
_ASSET_CLASS_BY_CATEGORY = {
    "stock": "equity",
    "etf": "etf",
    "index": "index",
    "futures": "futures",
    "crypto": "crypto",
}


@router.get("/instruments/search", response_model=list[InstrumentSearchHit])
def search_instruments(
    q: str,
    asset_class: str | None = None,
    category: str | None = None,
    exchange: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InstrumentSearchHit]:
    term = (q or "").strip()
    if not term:
        return []
    q_norm = term.lower()
    s = f"%{term}%"
    stmt = (
        select(Instrument)
        .where(Instrument.is_active.is_(True))
        .where(
            or_(
                Instrument.symbol.ilike(s),
                Instrument.display_name.ilike(s),
                Instrument.description.ilike(s),
            )
        )
    )
    if asset_class:
        stmt = stmt.where(Instrument.asset_class == asset_class)
    elif category:
        cat_lower = category.strip().lower()
        if cat_lower == "hong kong" or cat_lower == "hk":
            stmt = stmt.where(
                (Instrument.country == "HK") | (Instrument.exchange == "HKEX") | (Instrument.market == "HK")
            )
        elif cat_lower in _ASSET_CLASS_BY_CATEGORY:
            stmt = stmt.where(Instrument.asset_class == _ASSET_CLASS_BY_CATEGORY[cat_lower])
    if exchange:
        stmt = stmt.where(Instrument.exchange == exchange)

    rows = db.scalars(stmt.limit(100)).all()

    def score(inst: Instrument) -> int:
        sym = (inst.symbol or "").lower()
        name = (inst.display_name or "").lower()
        desc = (inst.description or "").lower()
        sc = 0
        if sym == q_norm:
            sc += 100
        elif sym.startswith(q_norm):
            sc += 70
        elif q_norm in sym:
            sc += 50
        if q_norm in name:
            sc += 30
        if q_norm in desc:
            sc += 10
        return sc

    ranked = sorted(rows, key=score, reverse=True)[:20]

    def _db_identity_key(inst: Instrument) -> tuple[str, str, str]:
        return (inst.symbol, inst.asset_class, (inst.exchange or "").strip().upper())

    hits_out: list[InstrumentSearchHit] | None = None

    threshold = max(1, int(getattr(settings, "instrument_search_min_local_before_external", 1) or 1))
    if len(ranked) >= threshold:
        logger.info(
            "instrument_search source=local q=%r count=%d threshold=%d",
            term[:80],
            len(ranked),
            threshold,
        )
    else:
        logger.info(
            "instrument_search source=local_insufficient q=%r count=%d threshold=%d — trying Twelve",
            term[:80],
            len(ranked),
            threshold,
        )
        filtered = filter_twelve_instrument_search_rows(
            term,
            asset_class=asset_class,
            category=category,
            exchange=exchange,
            max_rows=25,
        )
        n_twelve = len(filtered)
        if n_twelve == 0:
            logger.info(
                "instrument_search external_fallback_empty q=%r (Twelve returned no matching rows)",
                term[:80],
            )
        else:
            ins = upd = 0
            try:
                ins, upd = persist_twelve_instrument_rows(db, filtered, provider="external_api")
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("instrument_search external_persist_failed q=%r", term[:80])
                logger.info(
                    "instrument_search external_results_returned_without_persist "
                    "q=%r twelve_filtered=%d reason=commit_or_session_error",
                    term[:80],
                    n_twelve,
                )
                hits_out = [
                    InstrumentSearchHit(**d)
                    for d in twelve_rows_to_ephemeral_hit_dicts(filtered, q_norm=q_norm, limit=20)
                ]
            else:
                persisted = ins + upd
                if persisted == n_twelve and n_twelve > 0:
                    logger.info(
                        "instrument_search external_full_persist q=%r twelve_filtered=%d inserted=%d updated=%d",
                        term[:80],
                        n_twelve,
                        ins,
                        upd,
                    )
                elif 0 < persisted < n_twelve:
                    logger.info(
                        "instrument_search external_partial_persist "
                        "q=%r twelve_filtered=%d persisted_rows=%d inserted=%d updated=%d",
                        term[:80],
                        n_twelve,
                        persisted,
                        ins,
                        upd,
                    )
                elif n_twelve > 0 and persisted == 0:
                    logger.info(
                        "instrument_search external_results_returned_without_persist "
                        "q=%r twelve_filtered=%d reason=no_rows_saved",
                        term[:80],
                        n_twelve,
                    )

                if hits_out is None:
                    if persisted > 0:
                        rows2 = db.scalars(stmt.limit(100)).all()
                        ranked = sorted(rows2, key=score, reverse=True)[:20]
                        db_hits = [
                            InstrumentSearchHit(
                                id=str(r.id),
                                symbol=r.symbol,
                                display_name=r.display_name,
                                asset_class=r.asset_class,
                                market=r.market,
                                exchange=r.exchange,
                                description=r.description,
                                country=r.country,
                                currency=r.currency,
                                data_origin="local_db",
                            )
                            for r in ranked
                        ]
                        if 0 < persisted < n_twelve:
                            have = {_db_identity_key(r) for r in ranked}
                            missing = [r for r in filtered if twelve_row_identity_key(r) not in have]
                            if missing:
                                extra = twelve_rows_to_ephemeral_hit_dicts(
                                    missing, q_norm=q_norm, limit=max(0, 20 - len(db_hits))
                                )
                                hits_out = db_hits + [InstrumentSearchHit(**d) for d in extra]
                            else:
                                hits_out = db_hits
                        else:
                            hits_out = db_hits
                    else:
                        hits_out = [
                            InstrumentSearchHit(**d)
                            for d in twelve_rows_to_ephemeral_hit_dicts(filtered, q_norm=q_norm, limit=20)
                        ]

    logger.debug(
        "search_instruments q=%r asset_class=%r exchange=%r results=%d",
        q,
        asset_class,
        exchange,
        len(hits_out) if hits_out is not None else len(ranked),
    )

    if hits_out is not None:
        return hits_out

    return [
        InstrumentSearchHit(
            id=str(r.id),
            symbol=r.symbol,
            display_name=r.display_name,
            asset_class=r.asset_class,
            market=r.market,
            exchange=r.exchange,
            description=r.description,
            country=r.country,
            currency=r.currency,
            data_origin="local_db",
        )
        for r in ranked
    ]
