"""Journal and audit log Pydantic v2 schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.schemas.trade import (
    ExecutionResult,
    RawUserThesis,
    InterpretedTradeThesis,
    TradeDecision,
    TradeObjection,
    TradeVariant,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4() -> str:
    return str(uuid.uuid4())


class JournalEntry(BaseModel):
    """A complete, immutable record of a trade lifecycle — designed for future ML analysis."""

    entry_id: str = Field(default_factory=_uuid4)
    trade_id: str
    user_id: str
    timestamp: datetime = Field(default_factory=_now)

    # Trade content
    raw_thesis: RawUserThesis
    interpreted_thesis: Optional[InterpretedTradeThesis] = None
    variants_considered: list[TradeVariant] = Field(default_factory=list)
    objections_raised: list[TradeObjection] = Field(default_factory=list)
    final_decision: Optional[TradeDecision] = None
    execution_result: Optional[ExecutionResult] = None
    market_context_at_entry: Optional[Any] = None  # MarketContext

    # Phase 2+ ML hooks — populated retroactively or by future services
    user_mood_hint: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    outcome_pips: Optional[float] = None
    outcome_pnl: Optional[float] = None
    strategy_label: Optional[str] = None


class AuditLogEntry(BaseModel):
    """Structured audit event for replay and debugging."""

    log_id: str = Field(default_factory=_uuid4)
    timestamp: datetime = Field(default_factory=_now)
    event_type: str
    actor: str  # "user" | "system"
    details: dict
    trade_id: Optional[str] = None
