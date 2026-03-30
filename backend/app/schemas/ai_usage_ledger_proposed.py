"""
Proposed shape for a future ``ai_usage_ledger`` table.

**Not** a SQLAlchemy model and **not** registered with ``Base`` — avoids accidental DDL.
See ``docs/ai_usage_ledger.md`` for the full schema proposal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class AiUsageLedgerRow:
    user_id: uuid.UUID
    feature_key: str
    feature_tier: str
    provider: str
    model: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    estimated_cost: Optional[Decimal]
    credits_charged: int
    created_at: datetime
    id: Optional[uuid.UUID] = None
