"""
Entity price-chart event timeline: volatility day selection, demo official releases,
and placeholder news windows. Intended to be swapped for provider-backed pipelines later.

REAL: volatility ranking from OHLCV bars, unified point model, window time math.
PLACEHOLDER: official release seeding heuristic, news item text, AI summary responses.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import user_is_admin
from app.models.portfolio import Instrument, PortfolioEntity
from app.models.user import User
from app.schemas.entity_timeline import (
    AiCitationOut,
    AiSummaryResponse,
    TimelineAccessOut,
    TimelineNewsItemOut,
    TimelinePointOut,
    TimelinePointsResponse,
    TimelineWindowResponse,
)
from app.services.market_snapshots import resolve_ohlcv_bars


def timeline_can_interact(user: User) -> tuple[bool, str | None]:
    if user_is_admin(user):
        return True, "admin"
    paid = bool(getattr(user, "paid_access", False))
    bal = int(getattr(user, "credits_balance", 0) or 0)
    if paid and bal > 0:
        return True, "paid_and_credited"
    if not paid:
        return False, "need_paid_or_topup"
    return False, "need_paid_or_topup"


def timeline_access_out(user: User) -> TimelineAccessOut:
    can, reason = timeline_can_interact(user)
    return TimelineAccessOut(
        can_interact=can,
        is_admin=user_is_admin(user),
        paid_access=bool(getattr(user, "paid_access", False)),
        credits_balance=int(getattr(user, "credits_balance", 0) or 0),
        reason=reason,
    )


def _day_start_utc(ts: int) -> int:
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    d = dt.date()
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _safe_symbol(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not re.match(r"^[A-Z0-9.\-]{1,32}$", s):
        return ""
    return s


def compute_volatility_top_days(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Top ~10% of calendar days in range by intraday range % (high-low)/max(|open|,eps).
    Replaceable later (e.g. realized vol, gap-inclusive metrics).
    """
    if not bars:
        return []
    by_day: dict[int, list[dict[str, Any]]] = {}
    for b in bars:
        t = b.get("time")
        if t is None:
            continue
        t = int(t)
        if not t:
            continue
        d0 = _day_start_utc(t)
        by_day.setdefault(d0, []).append(b)

    days: list[dict[str, Any]] = []
    for d0 in sorted(by_day.keys()):
        daybars = by_day[d0]
        o = float(daybars[0].get("open") or 0)
        h = max(float(x.get("high") or 0) for x in daybars)
        low = min(float(x.get("low") or 0) for x in daybars)
        denom = max(abs(o), 1e-9)
        range_pct = (h - low) / denom
        days.append({"day_start": d0, "score": range_pct})

    n = len(days)
    if n < 3:
        return []

    k = max(1, math.ceil(n * 0.1))
    k = min(k, n)
    ranked = sorted(days, key=lambda x: float(x["score"]), reverse=True)[:k]
    return sorted(ranked, key=lambda x: int(x["day_start"]))


# --- Official release DEMO seed (replace with calendars per asset_class) ---
def _symbol_digest(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)


def seed_official_demo_points(symbol: str, asset_class: str, bars: list[dict[str, Any]]) -> list[int]:
    """
    Deterministic demo timestamps (day starts) for 'official' blue points.
    Not real calendar data — obvious in API label_hint / data_mode.
    """
    if not bars:
        return []
    times = sorted(int(b["time"]) for b in bars if b.get("time") is not None)
    t_min, t_max = times[0], times[-1]
    digest = _symbol_digest(symbol) + sum(ord(c) for c in (asset_class or "")) * 7
    out: list[int] = []
    # Roughly one point every ~14–21 days of span, max 8
    span = max(t_max - t_min, 86400)
    step = max(14 * 86400, span // 6)
    cur = t_min + (digest % 86400) * 17
    while cur <= t_max and len(out) < 8:
        d0 = _day_start_utc(cur)
        if t_min <= d0 <= t_max:
            out.append(d0)
        cur += step + ((digest >> (len(out) * 3)) % (4 * 86400))
    # Dedup
    seen: set[int] = set()
    uniq = []
    for d0 in sorted(out):
        if d0 not in seen:
            seen.add(d0)
            uniq.append(d0)
    return uniq[:6]


def resolve_timeline_asset_class(db: Session, entity: PortfolioEntity, symbol: str) -> str:
    """
    asset_class for demo official seeding: match primary or related row for this entity,
    then fall back to instruments catalog. Ensures compare rows (ETF, crypto, etc.) use
    their own class rather than the primary binding only.
    """
    sym = _safe_symbol(symbol)
    if not sym:
        return "unknown"
    if entity.instrument and _safe_symbol(entity.instrument.symbol) == sym:
        ac = (entity.instrument.asset_class or "").strip()
        return ac or "unknown"
    for ri in entity.related_instruments or []:
        inst = ri.instrument
        if inst and _safe_symbol(inst.symbol) == sym:
            ac = (inst.asset_class or "").strip()
            return ac or "unknown"
    row = db.scalar(select(Instrument).where(Instrument.symbol == sym).limit(1))
    if row:
        ac = (row.asset_class or "").strip()
        return ac or "unknown"
    if entity.instrument:
        ac = (entity.instrument.asset_class or "").strip()
        return ac or "unknown"
    return "unknown"


def build_timeline_points(
    db: Session,
    *,
    user: User,
    symbol: str,
    period: str,
    chart_scope: str,
    asset_class: str,
) -> TimelinePointsResponse:
    sym = _safe_symbol(symbol)
    access = timeline_access_out(user)
    if not sym:
        return TimelinePointsResponse(
            access=access,
            symbol=symbol or "",
            period=period.upper(),
            chart_scope=chart_scope,
            range_start=0,
            range_end=0,
            points=[],
            data_updated_at=None,
            data_source="stale_fallback",
            stale=True,
        )

    if not access.can_interact:
        return TimelinePointsResponse(
            access=access,
            symbol=sym,
            period=period.upper(),
            chart_scope=chart_scope,
            range_start=0,
            range_end=0,
            points=[],
            data_updated_at=None,
            data_source="stale_fallback",
            stale=True,
        )

    bars, snap, stale_ohlcv = resolve_ohlcv_bars(db, sym, period.upper() if period else "1M")
    lu = snap.last_success_at.isoformat() if snap and snap.last_success_at else None
    if not bars:
        return TimelinePointsResponse(
            access=access,
            symbol=sym,
            period=period.upper(),
            chart_scope=chart_scope,
            range_start=0,
            range_end=0,
            points=[],
            data_updated_at=lu,
            data_source="stale_fallback" if stale_ohlcv else "snapshot",
            stale=stale_ohlcv,
        )

    times = [int(b["time"]) for b in bars if b.get("time") is not None]
    r0, r1 = min(times), max(times)

    points: list[TimelinePointOut] = []

    for row in compute_volatility_top_days(bars):
        d0 = int(row["day_start"])
        pid = f"vol:{sym}:{d0}"
        points.append(
            TimelinePointOut(
                id=pid,
                point_type="volatility",
                time=d0,
                score=float(row["score"]),
                label_hint="high_range_day",
            )
        )

    official_days = seed_official_demo_points(sym, asset_class, bars)
    used_vol_days = {p.time for p in points if p.point_type == "volatility"}
    for d0 in official_days:
        if d0 in used_vol_days:
            continue
        pid = f"off:{sym}:{d0}"
        points.append(
            TimelinePointOut(
                id=pid,
                point_type="official",
                time=d0,
                score=None,
                label_hint="demo_official_release",
            )
        )

    points.sort(key=lambda p: (p.time, p.point_type))

    return TimelinePointsResponse(
        access=access,
        symbol=sym,
        period=period.upper(),
        chart_scope=chart_scope,
        range_start=r0,
        range_end=r1,
        points=points,
        data_updated_at=lu,
        data_source="stale_fallback" if stale_ohlcv else "snapshot",
        stale=stale_ohlcv,
    )


def _parse_point_id(point_id: str) -> tuple[str, str, int] | None:
    # vol:AAPL:1704067200 or off:BRK.B:1704067200 — split with maxsplit so symbols may contain dots
    raw = (point_id or "").strip()
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    kind, sym, ts_s = parts
    try:
        ts = int(ts_s)
    except ValueError:
        return None
    if kind not in ("vol", "off"):
        return None
    sym = _safe_symbol(sym)
    if not sym:
        return None
    return ("volatility" if kind == "vol" else "official", sym, ts)


def _window_bounds_iso(focus_ts: int) -> tuple[str, str]:
    """Anchor day ± half calendar day for UI copy (UTC)."""
    focus = datetime.fromtimestamp(focus_ts, tz=timezone.utc)
    start = focus.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=12)
    end = focus.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) + timedelta(hours=12)
    return start.isoformat(), end.isoformat()


def resolve_summary_window_bounds(
    focus_ts: int,
    summary_window: str,
    custom_start_iso: str | None,
    custom_end_iso: str | None,
) -> tuple[str, str, str]:
    """
    AI summary requested time span (UTC ISO). Third return is a short tag for placeholder copy.
    """
    focus = datetime.fromtimestamp(focus_ts, tz=timezone.utc)
    if summary_window == "point":
        ws, we = _window_bounds_iso(focus_ts)
        return ws, we, "point_window"
    if summary_window == "24h":
        start = focus - timedelta(hours=24)
        end = focus + timedelta(hours=24)
        return start.isoformat(), end.isoformat(), "24h"
    if summary_window == "72h":
        start = focus - timedelta(hours=36)
        end = focus + timedelta(hours=36)
        return start.isoformat(), end.isoformat(), "72h"
    if summary_window == "7d":
        start = focus - timedelta(days=3)
        end = focus + timedelta(days=4)
        return start.isoformat(), end.isoformat(), "7d"
    if summary_window == "custom":
        if not custom_start_iso or not custom_end_iso:
            raise ValueError("custom_start_iso and custom_end_iso required for custom window")
        for raw in (custom_start_iso, custom_end_iso):
            try:
                datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(f"Invalid ISO datetime: {raw}") from e
        return custom_start_iso, custom_end_iso, "custom"
    ws, we = _window_bounds_iso(focus_ts)
    return ws, we, "point_window"


def _placeholder_news_items(
    symbol: str,
    focus_ts: int,
    point_type: str,
    entity_terms: list[str],
) -> list[TimelineNewsItemOut]:
    """PLACEHOLDER news rows — swap for retrieval service later."""
    d = datetime.fromtimestamp(focus_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    term_snip = ", ".join(entity_terms[:3]) if entity_terms else "key narratives"
    base_id = hashlib.md5(f"{symbol}:{focus_ts}:{point_type}".encode()).hexdigest()[:12]

    items = [
        TimelineNewsItemOut(
            id=f"{base_id}-a",
            title=f"{symbol}: flow & positioning commentary ({d}) — sample",
            source_name="Demo wire",
            source_url=None,
            summary=(
                f"Placeholder item aligned to your terms ({term_snip}). "
                "A future pipeline will attach real headlines and links."
            ),
            sentiment="neutral",
            category="industry" if point_type == "volatility" else "official_release",
        ),
        TimelineNewsItemOut(
            id=f"{base_id}-b",
            title="Macro / policy headline window — sample",
            source_name="Demo policy desk",
            source_url="https://example.com/placeholder-story",
            summary="Illustrates regulator or institution announcement slots for this window.",
            sentiment="bearish" if point_type == "volatility" else "neutral",
            category="policy" if point_type == "official" else "macro",
        ),
        TimelineNewsItemOut(
            id=f"{base_id}-c",
            title="Geopolitical / risk tape note — sample",
            source_name="Demo world desk",
            source_url=None,
            summary="Room for conflict or shock-related items when providers are connected.",
            sentiment="neutral",
            category="conflict",
        ),
    ]
    return items


def get_timeline_window(
    *,
    user: User,
    point_id: str,
    entity_terms: list[str],
) -> TimelineWindowResponse | None:
    parsed = _parse_point_id(point_id)
    if not parsed:
        return None
    ptype, sym, focus_ts = parsed
    ws, we = _window_bounds_iso(focus_ts)
    items = _placeholder_news_items(sym, focus_ts, ptype, entity_terms)
    return TimelineWindowResponse(
        point_id=point_id,
        point_type="volatility" if ptype == "volatility" else "official",
        focus_time=focus_ts,
        window_start_iso=ws,
        window_end_iso=we,
        symbol=sym,
        items=items,
        data_mode="placeholder",
    )


def ai_summary_placeholder(
    *,
    provider: str,
    point_id: str,
    window: TimelineWindowResponse,
    summary_window: str = "point",
    custom_start_iso: str | None = None,
    custom_end_iso: str | None = None,
) -> AiSummaryResponse:
    """PLACEHOLDER multi-provider response — wire real routers later."""
    try:
        w_start, w_end, w_tag = resolve_summary_window_bounds(
            window.focus_time, summary_window, custom_start_iso, custom_end_iso
        )
    except ValueError as e:
        return AiSummaryResponse(
            status="error",
            provider=provider,
            interpretation=None,
            summary=str(e),
            citations=[],
            model_label=None,
            detail="invalid_window",
        )

    citations = [
        AiCitationOut(title=item.title, url=item.source_url)
        for item in window.items
        if item.source_url
    ]
    prov_label = {
        "gemini": "Google Gemini (not connected)",
        "openai": "OpenAI GPT (not connected)",
        "anthropic": "Anthropic Claude (not connected)",
        "qwen": "Qwen (not connected)",
    }.get(provider, provider)
    return AiSummaryResponse(
        status="placeholder",
        provider=provider,
        interpretation="mixed",
        summary=(
            f"[{prov_label}] Placeholder summary for {window.symbol}. "
            f"Summary time span ({w_tag}, UTC): {w_start} → {w_end}. "
            f"Focus day: {datetime.fromtimestamp(window.focus_time, tz=timezone.utc).date().isoformat()}. "
            "A future service will explain drivers using live news and model routing. "
            f"Point: {point_id}."
        ),
        citations=citations,
        model_label=prov_label,
        detail="Provider not wired; safe placeholder response.",
    )
