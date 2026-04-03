from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.routes import ai_routes
from app.core.plan_entitlements import AiAccessLevel, PlanCode
from app.models.user import User


def _admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="kw_test_admin",
        email="kw_admin@t.example",
        password_hash="x",
        credits_balance=0,
        plan_code=PlanCode.FREE.value,
        ai_access_level=AiAccessLevel.NONE.value,
        paid_access=False,
        is_admin=True,
        token_version=0,
        profile_name="",
    )


@pytest.fixture
def client_keyword_suggestions() -> TestClient:
    app = FastAPI()
    app.include_router(ai_routes.router, prefix="/api/ai")
    app.dependency_overrides[get_current_user] = lambda: _admin_user()
    yield TestClient(app)
    app.dependency_overrides.clear()


@patch("app.api.routes.ai_routes.settings")
@patch("app.api.routes.ai_routes.httpx.Client")
def test_keyword_suggestions_json_keywords(
    mock_client_cls: MagicMock,
    mock_settings: MagicMock,
    client_keyword_suggestions: TestClient,
) -> None:
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model = "gemini-1.5-flash"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"keywords": ["foo", "bar"]}'
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '{"keywords": ["foo", "bar"]}'}]}}],
    }
    mock_response.raise_for_status = MagicMock()

    inner = MagicMock()
    inner.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = None
    mock_client_cls.return_value = mock_cm

    r = client_keyword_suggestions.post("/api/ai/keyword-suggestions", json={"idea": "test narrative"})
    assert r.status_code == 200
    data = r.json()
    assert data == {"keywords": ["foo", "bar"]}
    inner.post.assert_called_once()
    called_url = inner.post.call_args[0][0]
    assert ":generateContent" in called_url
    assert "gemini-2.0-flash" in called_url


@patch("app.api.routes.ai_routes.settings")
@patch("app.api.routes.ai_routes.httpx.Client")
def test_keyword_suggestions_gemini_http_error_mapped(
    mock_client_cls: MagicMock,
    mock_settings: MagicMock,
    client_keyword_suggestions: TestClient,
) -> None:
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model = "gemini-2.0-flash"

    mock_error_response = MagicMock()
    mock_error_response.status_code = 404
    mock_error_response.text = '{"error":{"message":"not found"}}'

    req = httpx.Request("POST", "https://example.com/generateContent")

    def _raise_for_status() -> None:
        raise httpx.HTTPStatusError("404", request=req, response=mock_error_response)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = mock_error_response.text
    mock_response.raise_for_status = _raise_for_status

    inner = MagicMock()
    inner.post.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = inner
    mock_cm.__exit__.return_value = None
    mock_client_cls.return_value = mock_cm

    r = client_keyword_suggestions.post("/api/ai/keyword-suggestions", json={"idea": "x"})
    assert r.status_code == 502
    assert "404" in r.json()["detail"]
