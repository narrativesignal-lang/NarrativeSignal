"""
Entity price-chart event timeline: OHLCV volatility days + reserved official markers.

- Yellow (volatility): high range-move days; news is fetched on demand around the move with
  symbol/name/term relevance filtering (RSS). No official-signal mixing.

- Blue (official): only for future structured / high-confidence feeds (SEC calendar, etc.).
  RSS keyword classification is NOT used to place blue markers (prefer none over false positives).

PLACEHOLDER:
- AI summary text only (``ai_summary_placeholder``).
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.user_admin import user_is_admin
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
from app.services.entity_news_service import fetch_entity_news_by_query
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


# Volatility news window: ±12h around noon UTC of the marker day (24h total). Override via env later if needed.
VOLATILITY_NEWS_HALF_HOURS = 12

_NAME_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "company",
        "co",
        "ltd",
        "limited",
        "plc",
        "llc",
        "lp",
        "group",
        "holdings",
        "holding",
        "international",
        "technologies",
        "technology",
        "systems",
        "services",
        "global",
        "ordinary",
        "shares",
        "class",
    }
)

# Headlines must match these (regex) to appear in an *official* (blue) event panel. Not used to place markers.
_EQ_OFFICIAL_HEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b10[\s.-]?(k|q)\b", re.I),
    re.compile(r"\b10k\b", re.I),
    re.compile(r"\b10q\b", re.I),
    re.compile(r"\b8[\s.-]?k\b", re.I),
    re.compile(r"\bearnings\b", re.I),
    re.compile(r"\beps\b", re.I),
    re.compile(r"\bguidance\b", re.I),
    re.compile(r"\boutlook\b", re.I),
    re.compile(r"\bmerger\b|\bacquisition\b|\bacquires?\b|\btakeover\b", re.I),
    re.compile(r"\bpartnership\b|\bstrategic\s+partnership\b", re.I),
)

_MACRO_OFFICIAL_HEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfederal\s+reserve\b|\bthe\s+fed\b|\bfomc\b", re.I),
    re.compile(r"\becb\b|\beuropean\s+central\s+bank\b", re.I),
    re.compile(r"\bboj\b|\bbank\s+of\s+japan\b", re.I),
    re.compile(r"\brate\s+(cut|hike|decision)\b|\binterest\s+rates?\b", re.I),
    re.compile(r"\bcpi\b", re.I),
    re.compile(r"\bnfp\b|\bnon[-\s]?farm\b", re.I),
    re.compile(r"\bgdp\b", re.I),
    re.compile(r"\bpmi\b", re.I),
)


def _significant_name_tokens(*names: str | None) -> set[str]:
    out: set[str] = set()
    for raw in names:
        if not raw:
            continue
        for w in re.split(r"[^\w]+", raw.lower()):
            if len(w) >= 4 and w not in _NAME_STOPWORDS:
                out.add(w)
    return out


def _volatility_relevance_ok(title: str, snippet: str, sym: str, entity: PortfolioEntity, entity_terms: list[str]) -> bool:
    """Require symbol, company-name token, or strong keyword overlap — reduce generic RSS noise."""
    h = f"{title} {snippet}".lower()
    if not h.strip():
        return False

    sym_u = _safe_symbol(sym).lower()
    if sym_u:
        if sym_u in h:
            return True
        if "." in sym_u and sym_u.split(".")[0] in h:
            return True
        if re.search(rf"(?:^|[^\w]){re.escape(sym_u)}(?:[^\w]|$)", h):
            return True

    inst = entity.instrument
    name_tokens = _significant_name_tokens(
        inst.display_name if inst else None,
        entity.name,
    )
    if any(t in h for t in name_tokens):
        return True

    for term in entity_terms:
        t = term.strip().lower()
        if len(t) < 3:
            continue
        if t not in h:
            continue
        if len(t) >= 5:
            return True
        if sym_u and sym_u in h:
            return True
        if any(nt in h for nt in name_tokens):
            return True
    return False


def _official_headline_matches(asset_class: str, title: str, snippet: str) -> bool:
    text = f"{title} {snippet}"
    ac = (asset_class or "").lower().strip()
    if ac in {"macro", "fx", "rates", "bond", "commodity"}:
        return any(p.search(text) for p in _MACRO_OFFICIAL_HEADLINE_PATTERNS)
    return any(p.search(text) for p in _EQ_OFFICIAL_HEADLINE_PATTERNS)


def _build_volatility_news_query(sym: str, entity: PortfolioEntity, entity_terms: list[str]) -> str:
    chunks: list[str] = []
    s = _safe_symbol(sym)
    if s:
        chunks.append(s)
    inst = entity.instrument
    if inst:
        dn_inst = (inst.display_name or "").strip()
        if dn_inst and dn_inst.upper() != s.upper():
            chunks.append(dn_inst if " " not in dn_inst else f'"{dn_inst}"')
    en = (entity.name or "").strip()
    if en and en.lower() not in {c.lower() for c in chunks}:
        chunks.append(en if " " not in en else f'"{en}"')
    for t in entity_terms:
        tt = t.strip()
        if tt and tt.lower() not in {c.lower().strip('"') for c in chunks}:
            chunks.append(tt)
    chunks = chunks[:10]
    if not chunks:
        return ""
    if len(chunks) == 1:
        return f"{chunks[0]} stock"
    return " OR ".join(chunks[:8])


def _volatility_news_window_bounds(focus_ts: int, half_hours: int = VOLATILITY_NEWS_HALF_HOURS) -> tuple[str, str]:
    """±half_hours around noon UTC of the volatility day (focus_ts = day start)."""
    noon = focus_ts + 12 * 3600
    delta = half_hours * 3600
    start = datetime.fromtimestamp(noon - delta, tz=timezone.utc)
    end = datetime.fromtimestamp(noon + delta, tz=timezone.utc)
    return start.isoformat(), end.isoformat()


def _pub_in_window(pub_iso: str | None, ws_iso: str, we_iso: str) -> bool:
    if not pub_iso:
        return False
    try:
        pub = datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
        ws = datetime.fromisoformat(ws_iso.replace("Z", "+00:00"))
        we = datetime.fromisoformat(we_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    return ws <= pub <= we


def _items_from_raw_for_window(
    raw: list[dict[str, Any]],
    ws_iso: str,
    we_iso: str,
    *,
    sym: str,
    entity: PortfolioEntity,
    entity_terms: list[str],
    asset_class: str,
    point_type: str,
) -> tuple[list[TimelineNewsItemOut], str]:
    """
    Filter by time window, relevance, and (for official) strict headline signal patterns.
    Returns (items, news_status) where news_status is has_items | no_relevant_news.
    """

    def _pub_ts(it: dict[str, Any]) -> float:
        p = it.get("published_at")
        if not p or not isinstance(p, str):
            return 0.0
        try:
            return datetime.fromisoformat(p.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    raw_sorted = sorted([x for x in raw if isinstance(x, dict)], key=_pub_ts, reverse=True)
    news_out: list[TimelineNewsItemOut] = []
    seen: set[str] = set()

    for it in raw_sorted:
        pub = it.get("published_at")
        if not isinstance(pub, str) or not pub:
            continue
        if not _pub_in_window(pub, ws_iso, we_iso):
            continue

        title = (it.get("title") or "").strip() or "(no title)"
        snippet = str(it.get("snippet") or "").strip()

        if not _volatility_relevance_ok(title, snippet, sym, entity, entity_terms):
            continue
        if point_type == "official" and not _official_headline_matches(asset_class, title, snippet):
            continue

        dedupe = hashlib.sha256(
            f"{title}|{it.get('url') or ''}|{pub}".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:18]
        if dedupe in seen:
            continue
        seen.add(dedupe)

        news_out.append(
            TimelineNewsItemOut(
                id=f"rss-{dedupe}",
                title=title[:300],
                source_name=(it.get("source") or "—")[:120],
                source_url=it.get("url") if isinstance(it.get("url"), str) else None,
                summary=((snippet) or "—")[:500],
                sentiment="neutral",
                category="official_signal" if point_type == "official" else "volatility_context",
            )
        )

    status = "has_items" if news_out else "no_relevant_news"
    return news_out, status


def resolve_timeline_asset_class(db: Session, entity: PortfolioEntity, symbol: str) -> str:
    """
    Resolve asset class for the chart symbol: primary/related instruments, then catalog.
    Used for official-event headline routing when blue markers exist.
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
            official_events_available=False,
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
            official_events_available=False,
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

    # Blue / official markers: reserved for structured feeds (SEC, economic calendar APIs).
    # Do not infer from RSS; omit rather than show false causal links.

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
        official_events_available=False,
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


def get_timeline_window(
    *,
    db: Session,
    entity: PortfolioEntity,
    _user: User,
    point_id: str,
    entity_terms: list[str],
) -> TimelineWindowResponse | None:
    parsed = _parse_point_id(point_id)
    if not parsed:
        return None
    ptype, sym, focus_ts = parsed
    asset_class = resolve_timeline_asset_class(db, entity, sym)

    if ptype == "volatility":
        ws, we = _volatility_news_window_bounds(focus_ts)
        query = _build_volatility_news_query(sym, entity, entity_terms)
        if not query:
            return TimelineWindowResponse(
                point_id=point_id,
                point_type="volatility",
                focus_time=focus_ts,
                window_start_iso=ws,
                window_end_iso=we,
                symbol=sym,
                items=[],
                data_mode="live",
                news_status="no_relevant_news",
                status_message="No relevant news found for this move",
            )
        raw, _q, err, _hit = fetch_entity_news_by_query(
            entity_id=str(entity.id),
            query=query,
            limit=80,
        )
        if err == "fetch_failed":
            return TimelineWindowResponse(
                point_id=point_id,
                point_type="volatility",
                focus_time=focus_ts,
                window_start_iso=ws,
                window_end_iso=we,
                symbol=sym,
                items=[],
                data_mode="live",
                news_status="fetch_failed",
                status_message="News could not be loaded for this window. Try again later.",
            )
        items, _filt = _items_from_raw_for_window(
            raw,
            ws,
            we,
            sym=sym,
            entity=entity,
            entity_terms=entity_terms,
            asset_class=asset_class,
            point_type="volatility",
        )
        return TimelineWindowResponse(
            point_id=point_id,
            point_type="volatility",
            focus_time=focus_ts,
            window_start_iso=ws,
            window_end_iso=we,
            symbol=sym,
            items=items,
            data_mode="live",
            news_status="has_items" if items else "no_relevant_news",
            status_message=None if items else "No relevant news found for this move",
        )

    # official / blue — same fetch as volatility; strict headline patterns applied in _items_from_raw_for_window
    # (avoid Google RSS "AND" fragility; prefer local high-confidence filtering).
    ws_o, we_o = _volatility_news_window_bounds(focus_ts)
    query_o = _build_volatility_news_query(sym, entity, entity_terms)
    if not query_o:
        return TimelineWindowResponse(
            point_id=point_id,
            point_type="official",
            focus_time=focus_ts,
            window_start_iso=ws_o,
            window_end_iso=we_o,
            symbol=sym,
            items=[],
            data_mode="live",
            news_status="no_relevant_news",
            status_message="No relevant news found for this move",
        )
    raw_o, _q2, err_o, _hit2 = fetch_entity_news_by_query(
        entity_id=str(entity.id),
        query=query_o,
        limit=80,
    )
    if err_o == "fetch_failed":
        return TimelineWindowResponse(
            point_id=point_id,
            point_type="official",
            focus_time=focus_ts,
            window_start_iso=ws_o,
            window_end_iso=we_o,
            symbol=sym,
            items=[],
            data_mode="live",
            news_status="fetch_failed",
            status_message="News could not be loaded for this window. Try again later.",
        )
    items_o, _st_o = _items_from_raw_for_window(
        raw_o,
        ws_o,
        we_o,
        sym=sym,
        entity=entity,
        entity_terms=entity_terms,
        asset_class=asset_class,
        point_type="official",
    )
    return TimelineWindowResponse(
        point_id=point_id,
        point_type="official",
        focus_time=focus_ts,
        window_start_iso=ws_o,
        window_end_iso=we_o,
        symbol=sym,
        items=items_o,
        data_mode="live",
        news_status="has_items" if items_o else "no_relevant_news",
        status_message=None
        if items_o
        else "No headlines matched official-event criteria for this window.",
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
