from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.platform_tz import now_platform

SCHEDULE_TYPES = ("standard_monitor", "ai_alert", "ai_report", "general_alert")
MODEL_OPTIONS = ("gemini", "gpt", "claude", "grok", "qwen")


def _cron_interval_minutes(cron: str) -> float:
    from croniter import croniter

    base = now_platform()
    itr = croniter(cron.strip(), base)
    t0 = itr.get_next(datetime)
    t1 = itr.get_next(datetime)
    return (t1 - t0).total_seconds() / 60.0


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cron: str = Field(min_length=5, max_length=80)
    group_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    bucket_minutes: int = Field(60, ge=1, le=1440)
    is_active: bool = True
    schedule_type: str = Field(default="standard_monitor")
    label: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=40)
    impact_threshold: int | None = Field(default=None, ge=0, le=100)
    linked_assets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def standard_monitor_news_minimum_hourly(self) -> ScheduleCreate:
        """Standard / news-adjacent monitoring: at most once per hour; aggregation window ≥ 60 min."""
        st = (self.schedule_type or "standard_monitor").strip()
        if st != "standard_monitor":
            return self
        if self.bucket_minutes < 60:
            raise ValueError(
                "Aggregation window must be at least 60 minutes for standard monitoring."
            )
        try:
            step = _cron_interval_minutes(self.cron)
        except Exception as e:
            raise ValueError(
                "Invalid monitoring timing rule. Use five parts (minute hour day month weekday), "
                "for example 0 * * * * for hourly."
            ) from e
        if step < 60.0 - 1e-6:
            raise ValueError(
                "Standard monitoring may run at most once per hour. Widen the timing rule (for example hourly)."
            )
        return self


class EntityLabel(BaseModel):
    """Resolved entity for schedule display (id, name, symbol from primary instrument)."""
    id: str
    name: str
    symbol: str


class ScheduleOut(BaseModel):
    id: str
    name: str
    cron: str
    group_ids: list[str]
    entity_ids: list[str]
    entity_labels: list[EntityLabel] = Field(default_factory=list)
    bucket_minutes: int
    is_active: bool
    status: str
    schedule_type: str = "standard_monitor"
    label: str | None = None
    model: str | None = None
    impact_threshold: int | None = None
    linked_assets: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

