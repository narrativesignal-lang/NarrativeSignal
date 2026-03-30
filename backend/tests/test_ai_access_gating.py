from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.ai_access import (
    AI_BACKGROUND_SKIP_DETAIL,
    AI_FEATURES_FORBIDDEN_DETAIL,
    AI_RUN_SKIP_REASON_CODE,
    AI_SCHEDULE_TYPES,
    can_use_paid_ai,
)
from app.models.monitoring import SCHEDULE_TYPES
from app.models.user import User
from app.services.ai.service import analyze_documents
from app.services.ai_alert import run_ai_alert_pipeline, run_ai_report_pipeline


def _user(*, is_admin: bool) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.example",
        password_hash="x",
        credits_balance=10_000,
        paid_access=True,
        is_admin=is_admin,
        token_version=0,
        profile_name="",
    )


def test_can_use_paid_ai_true_for_admin() -> None:
    assert can_use_paid_ai(_user(is_admin=True)) is True


def test_can_use_paid_ai_false_for_non_admin_even_with_paid_flag() -> None:
    u = _user(is_admin=False)
    u.paid_access = True
    u.credits_balance = 99_999
    assert can_use_paid_ai(u) is False


def test_ai_schedule_types_frozen_set() -> None:
    assert AI_SCHEDULE_TYPES == frozenset({"ai_alert", "ai_report", "general_alert"})


def test_ai_forbidden_detail_stable() -> None:
    assert AI_FEATURES_FORBIDDEN_DETAIL == "AI features are currently available to admin only."


def test_background_skip_detail_includes_forbidden_message() -> None:
    assert AI_FEATURES_FORBIDDEN_DETAIL in AI_BACKGROUND_SKIP_DETAIL


def test_ai_schedule_types_are_valid_schedule_type_strings() -> None:
    for st in AI_SCHEDULE_TYPES:
        assert st in SCHEDULE_TYPES


def test_ai_run_skip_reason_code_stable() -> None:
    assert AI_RUN_SKIP_REASON_CODE == "ai_requires_admin"


def test_analyze_documents_returns_zero_without_acting_user_id() -> None:
    db = MagicMock()
    gid = uuid.uuid4()
    did = uuid.uuid4()
    n = analyze_documents(db=db, group_id=gid, document_ids=[did], acting_user_id=None)
    assert n == 0
    db.get.assert_not_called()


def test_analyze_documents_skips_non_admin() -> None:
    db = MagicMock()
    uid = uuid.uuid4()
    db.get.return_value = _user(is_admin=False)
    gid = uuid.uuid4()
    did = uuid.uuid4()
    n = analyze_documents(db=db, group_id=gid, document_ids=[did], acting_user_id=uid)
    assert n == 0


@patch("app.services.ai.service.get_provider")
def test_analyze_documents_invokes_provider_for_admin(mock_gp: MagicMock) -> None:
    db = MagicMock()
    uid = uuid.uuid4()
    owner = _user(is_admin=True)
    db.get.return_value = owner

    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.title = "T"
    doc.content = "body"

    db.scalars.return_value.all.return_value = [doc]
    db.scalar.return_value = None

    prov = MagicMock()
    prov.provider = "openai"
    prov.model = "gpt-test"
    prov.analyze.return_value = MagicMock(
        provider="openai",
        model="gpt-test",
        sentiment_label="neu",
        sentiment_score=0.0,
        narrative_summary="s",
        detected_events=[],
    )
    mock_gp.return_value = prov

    gid = uuid.uuid4()
    did = doc.id
    n = analyze_documents(db=db, group_id=gid, document_ids=[did], acting_user_id=uid)
    assert n == 1
    prov.analyze.assert_called_once()


def test_run_ai_alert_pipeline_skips_non_admin() -> None:
    db = MagicMock()
    uid = uuid.uuid4()
    db.get.return_value = _user(is_admin=False)
    out = run_ai_alert_pipeline(
        db=db,
        user_id=uid,
        schedule_id=None,
        schedule_type="ai_alert",
        group_ids=[],
        entity_ids=[],
        linked_assets=[],
        threshold=60,
        label=None,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == AI_RUN_SKIP_REASON_CODE
    assert out.get("alerts_triggered", 0) == 0
    db.add.assert_not_called()


def test_run_ai_report_pipeline_skips_non_admin() -> None:
    db = MagicMock()
    uid = uuid.uuid4()
    db.get.return_value = _user(is_admin=False)
    out = run_ai_report_pipeline(
        db=db,
        user_id=uid,
        schedule_id=None,
        schedule_type="ai_report",
        group_ids=[],
        entity_ids=[],
        linked_assets=[],
        label=None,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == AI_RUN_SKIP_REASON_CODE
    assert out.get("report_created", 0) == 0
