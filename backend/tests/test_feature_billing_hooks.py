from __future__ import annotations

import uuid

from app.core.feature_access import FeatureKey
from app.core.feature_billing_hooks import (
    can_consume_feature,
    charge_feature_credits,
    estimate_feature_credit_cost,
)
from app.models.user import User


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        username="u_test",
        email="t@example.com",
        password_hash="x",
        credits_balance=0,
    )


def test_can_consume_feature_stub_always_true() -> None:
    assert can_consume_feature(_user(), FeatureKey.KEYWORD_SUGGESTIONS, estimated_credits=999) is True


def test_estimate_feature_credit_cost_stub_zero() -> None:
    assert estimate_feature_credit_cost(FeatureKey.DOCUMENT_LLM_ANALYSIS, tokens=1_000) == 0


def test_charge_feature_credits_stub_noop() -> None:
    u = _user()
    before = u.credits_balance
    charge_feature_credits(u, FeatureKey.KEYWORD_SUGGESTIONS, credits=50)
    assert u.credits_balance == before
