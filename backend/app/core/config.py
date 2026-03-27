from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

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
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

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


settings = Settings()

