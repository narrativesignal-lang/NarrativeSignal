"""
Entity 3D chart data: time × relative search trend (0–100) × coverage volume (counts).

Mock implementations are deterministic (stable per entity + terms + date).
Replace with real providers:
  - search trend: Google Trends / pytrends / third-party relative index — NOT absolute search volume.
  - coverage: DB aggregation of news/docs matching entity terms per calendar day.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_CHART3D_RANGE_DAYS: dict[str, int] = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
}


def normalize_chart_3d_range(range_key: str) -> str:
    k = (range_key or "1m").strip().lower()
    return k if k in _CHART3D_RANGE_DAYS else "1m"


def _terms_seed(terms: list[str]) -> str:
    return "|".join(sorted((t or "").strip().lower() for t in terms)) or "entity"


def _iter_chart3d_dates(range_key: str) -> list[str]:
    """Oldest → newest calendar days (UTC midnight)."""
    rk = normalize_chart_3d_range(range_key)
    days = _CHART3D_RANGE_DAYS[rk]
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[str] = []
    for i in range(days - 1, -1, -1):
        d = now - timedelta(days=i)
        out.append(d.strftime("%Y-%m-%d"))
    return out


def get_entity_search_trend_timeseries(terms: list[str], entity_id: str, range_key: str) -> list[tuple[str, float]]:
    """
    Relative search interest index 0–100 (Google Trends–style).
    Does not represent absolute search volume.
    """
    seed = _terms_seed(terms)
    eid = str(entity_id)
    points: list[tuple[str, float]] = []
    for day_str in _iter_chart3d_dates(range_key):
        h = hash((seed, eid, day_str, "search_trend_index"))
        search_trend = float(h % 101)
        points.append((day_str, round(search_trend, 1)))
    return points


def get_entity_coverage_timeseries(terms: list[str], entity_id: str, range_key: str) -> list[tuple[str, float]]:
    """
    Count of news/documents matching entity terms per calendar day.
    Currently deterministic mock; replace with DB query when coverage index exists.
    """
    seed = _terms_seed(terms)
    eid = str(entity_id)
    points: list[tuple[str, float]] = []
    for day_str in _iter_chart3d_dates(range_key):
        coverage_volume = coverage_volume_mock_for_day(terms, entity_id, day_str)
        points.append((day_str, round(coverage_volume, 1)))
    return points


def coverage_volume_mock_for_day(terms: list[str], entity_id: str, day_str: str) -> float:
    """Deterministic mock coverage count (only used when DB + dedup have no coverage)."""
    seed = _terms_seed(terms)
    eid = str(entity_id)
    h = hash((seed, eid, day_str, "coverage_doc_count"))
    return float((h % 55) + 8)


def build_chart_3d_points(terms: list[str], entity_id: str, range_key: str) -> list[dict[str, float | str]]:
    """Aligned series for API: one row per date."""
    st = get_entity_search_trend_timeseries(terms, entity_id, range_key)
    cv = get_entity_coverage_timeseries(terms, entity_id, range_key)
    if len(st) != len(cv):
        raise RuntimeError("search trend and coverage series length mismatch")
    out: list[dict[str, float | str]] = []
    for i in range(len(st)):
        d1, trend = st[i]
        d2, cov = cv[i]
        if d1 != d2:
            raise RuntimeError("date alignment error in chart 3d")
        out.append(
            {
                "date": d1,
                "search_trend": trend,
                "coverage_volume": cov,
            }
        )
    return out
