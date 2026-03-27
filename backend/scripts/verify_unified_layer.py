"""
Sanity checks for narrative_metrics + OHLCV resolution (no DB).
Run from repo root: python backend/scripts/verify_unified_layer.py
Or: cd backend && python scripts/verify_unified_layer.py
"""

from __future__ import annotations


def main() -> None:
    from app.services.narrative_metrics import (
        range_key_from_quadrant_history_period,
        range_key_from_series_period,
        trend_label_from_momenta,
    )

    assert trend_label_from_momenta(1.0, 1.0, 0.0) == "Rising"
    assert trend_label_from_momenta(-1.0, -1.0, 0.0) == "Fading"
    assert trend_label_from_momenta(0.0, 0.0, 26.0) == "Spike"
    assert trend_label_from_momenta(0.0, 0.0, 0.0) == "Neutral"

    assert range_key_from_series_period("1M") == "1m"
    assert range_key_from_series_period("6M") == "3m"
    assert range_key_from_quadrant_history_period("1M") == "1m"
    assert range_key_from_quadrant_history_period("MAX") == "3m"

    from app.services.market_snapshots import resolve_ohlcv_bars
    from unittest.mock import MagicMock

    db = MagicMock()
    snap = MagicMock()
    snap.bars = {"bars": [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]}
    snap.is_stale = False
    snap.last_success_at = None

    db.get = MagicMock(return_value=snap)
    bars, out_snap, stale = resolve_ohlcv_bars(db, "TEST", "1M")
    assert len(bars) == 1
    assert out_snap is snap
    assert stale is False

    print("verify_unified_layer: OK")


if __name__ == "__main__":
    main()
