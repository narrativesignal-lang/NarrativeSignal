"""Pytest configuration: disable heavy app startup for API tests."""

from __future__ import annotations

import os

# Minimal env so `app.core.config.settings` loads without a real `.env` in CI.
# Docker-first defaults (override REDIS_URL / DATABASE_URL when running pytest on the host).
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/15")
os.environ.setdefault("JWT_SECRET", "pytest-jwt-secret-at-least-32-chars-long!!")

import pytest


@pytest.fixture
def no_app_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.init_db", lambda: None)
    monkeypatch.setattr("app.main._seed_admin_if_missing", lambda: None)
    monkeypatch.setattr("app.main._seed_instruments_if_empty", lambda: None)
    monkeypatch.setattr("app.main._ensure_local_instruments", lambda: None)
