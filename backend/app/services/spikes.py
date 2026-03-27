from __future__ import annotations

from datetime import datetime
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.index_point import IndexPoint
from app.models.spike_event import SpikeEvent


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return sqrt(var)


def detect_and_store_spikes(
    *,
    db: Session,
    group_id,
    point: IndexPoint,
    prev: IndexPoint | None,
) -> int:
    """
    Spike rules (MVP):
    - volume_spike: zscore(volume vs last 24 buckets) >= 2.5 and volume >= 5
    - acceleration_spike: d2 >= 10 (and abs(d2) noticeably large)
    - sentiment_shift: change in (pos-neg)/volume >= 0.6 with volume >= 5
    """
    created = 0
    bucket = point.bucket_start

    # Avoid duplicate spike rows for same bucket+kind
    existing_kinds = set(
        db.scalars(select(SpikeEvent.kind).where(SpikeEvent.group_id == group_id, SpikeEvent.bucket_start == bucket)).all()
    )

    # Volume spike vs history
    history = db.scalars(
        select(IndexPoint)
        .where(IndexPoint.group_id == group_id, IndexPoint.bucket_start < bucket)
        .order_by(IndexPoint.bucket_start.desc())
        .limit(24)
    ).all()
    hist_vol = [float(p.mention_volume) for p in history if p.mention_volume is not None]
    if len(hist_vol) >= 6 and point.mention_volume >= 5 and "volume_spike" not in existing_kinds:
        mean = sum(hist_vol) / len(hist_vol)
        sd = _std(hist_vol)
        if sd > 0:
            z = (point.mention_volume - mean) / sd
            if z >= 2.5:
                db.add(
                    SpikeEvent(
                        group_id=group_id,
                        bucket_start=bucket,
                        kind="volume_spike",
                        score=float(z),
                        details={"mean": mean, "std": sd, "volume": point.mention_volume, "n": len(hist_vol)},
                    )
                )
                db.commit()
                created += 1

    # Acceleration spike (second derivative)
    if abs(point.d2) >= 10 and "acceleration_spike" not in existing_kinds:
        db.add(
            SpikeEvent(
                group_id=group_id,
                bucket_start=bucket,
                kind="acceleration_spike",
                score=float(point.d2),
                details={"d2": point.d2, "d1": point.d1, "momentum": point.momentum},
            )
        )
        db.commit()
        created += 1

    # Sentiment shift based on count-derived index
    def s_index(p: IndexPoint) -> float:
        total = max(1, int(p.mention_volume))
        return (p.sentiment_positive - p.sentiment_negative) / total

    if prev and point.mention_volume >= 5 and "sentiment_shift" not in existing_kinds:
        delta = s_index(point) - s_index(prev)
        if abs(delta) >= 0.6:
            db.add(
                SpikeEvent(
                    group_id=group_id,
                    bucket_start=bucket,
                    kind="sentiment_shift",
                    score=float(delta),
                    details={"prev": s_index(prev), "cur": s_index(point), "delta": delta},
                )
            )
            db.commit()
            created += 1

    return created

