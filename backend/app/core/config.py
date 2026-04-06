from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Underscore-free Gemini IDs for :generateContent often 404; map legacy env values to a current model.
_GEMINI_REST_MODEL_ALIASES: dict[str, str] = {
    "gemini-1.5-flash": "gemini-2.0-flash",
    "gemini-1.5-flash-001": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-2.0-flash",
    "gemini-pro": "gemini-2.0-flash",
}


def resolve_gemini_rest_model_id(configured: str | None) -> str:
    """REST path segment for ``.../models/{id}:generateContent`` (not a secret)."""
    m = (configured or "").strip()
    if not m:
        m = "gemini-2.0-flash"
    return _GEMINI_REST_MODEL_ALIASES.get(m, m)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

    # Comma-separated browser origins for CORS. Empty = none (set per deployment, e.g. in docker-compose).
    cors_allow_origins: str = ""

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_issuer: str = "narrative-platform"
    # For local development we prefer a long-lived access token to reduce
    # re-login friction. Override via env in prod as needed.
    access_token_expire_minutes: int = 60 * 24 * 7
    refresh_token_expire_days: int = 30

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    # Optional override; default chat URL is derived in code when unset.
    openai_chat_completions_url: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    default_monitoring_cron: str = "*/60 * * * *"

    # Google Trends (pytrends): optional HTTP(S) proxy to reduce rate limits / geo blocks
    trends_proxy_url: str | None = None
    trends_default_timeframe: str = "today 6-m"
    trends_request_sleep_seconds: float = 1.5

    # Optional admin lock (comma-separated). Empty = no extra check; only users.is_admin is used.
    # If set, user must have is_admin=True AND match at least one list (username is OR email if both set).
    admin_usernames: str = ""
    admin_emails: str = ""

    # Twelve Data (optional): market search / quote / time_series
    twelve_api_key: str | None = None
    # Twelve global limiter (all code paths): at most 1 request / 10s and 6 / minute.
    twelve_global_min_interval_seconds: float = 10.0
    twelve_global_max_per_minute: int = 6

    # Worker task guards to avoid same-minute provider bursts.
    twelve_task_guard_seconds: int = 45
    twelve_secondary_skip_after_primary_seconds: int = 300

    # Startup warmups (API process): when enabled, may trigger external provider calls in background.
    # Local development default should be False to avoid rate-limit collisions.
    enable_startup_warmups: bool = False

    # Massive: supplemental market data only (background jobs). Never primary; never user-facing.
    massive_api_key: str | None = None
    # Hard global quotas (Redis); enforced before every Massive HTTP call.
    massive_quota_per_minute: int = 30
    massive_quota_per_day: int = 2000

    # Portfolio GET /instruments/search: call Twelve only when local row count is below this (default: empty DB only)
    instrument_search_min_local_before_external: int = 1

    # Yahoo/yfinance fallback pacing (worker + snapshot refresh). Cooldown floor is 600s in code.
    yahoo_fallback_min_interval_seconds: float = 1.25
    yahoo_rate_limit_cooldown_seconds: int = 1200


settings = Settings()

