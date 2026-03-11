"""Trade-lifecycle Pydantic v2 schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4() -> str:
    return str(uuid.uuid4())


# ── Enumerations ──────────────────────────────────────────────────────────────


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    INTAKE = "INTAKE"
    DEBATING = "DEBATING"
    REFINING = "REFINING"
    READY = "READY"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ObjectionSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ObjectionCategory(str, Enum):
    RISK = "RISK"
    TIMING = "TIMING"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    SIZING = "SIZING"
    GENERAL = "GENERAL"


# ── Core trade models ─────────────────────────────────────────────────────────


class RawUserThesis(BaseModel):
    """The raw, unprocessed message text from the user."""

    raw_text: str
    timestamp: datetime = Field(default_factory=_now)
    user_id: str


class InterpretedTradeThesis(BaseModel):
    """Structured interpretation of the user's raw thesis."""

    symbol: Optional[str] = None
    direction: Optional[TradeDirection] = None
    rationale: Optional[str] = None
    confidence_hint: Optional[str] = None
    timeframe_hint: Optional[str] = None
    entry_price_hint: Optional[float] = None
    stop_loss_hint: Optional[float] = None
    take_profit_hint: Optional[float] = None
    risk_pct_hint: Optional[float] = None


class TradeVariant(BaseModel):
    """A specific, fully-specified trade setup (one of potentially many alternatives)."""

    variant_id: str = Field(default_factory=_uuid4)
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    risk_pct: float
    risk_reward_ratio: float
    estimated_profit: Optional[float] = None
    estimated_loss: Optional[float] = None
    rationale: str
    source: str  # "user" | "system" | "debate"
    created_at: datetime = Field(default_factory=_now)


class TradeObjection(BaseModel):
    """A concern or objection raised during the debate phase."""

    objection_id: str = Field(default_factory=_uuid4)
    severity: ObjectionSeverity
    category: ObjectionCategory
    description: str
    suggestion: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class TradeDraft(BaseModel):
    """The mutable state of a trade idea from intake through confirmation."""

    draft_id: str = Field(default_factory=_uuid4)
    user_id: str
    status: TradeStatus = TradeStatus.INTAKE
    raw_thesis: RawUserThesis
    interpreted_thesis: Optional[InterpretedTradeThesis] = None
    variants: list[TradeVariant] = Field(default_factory=list)
    objections: list[TradeObjection] = Field(default_factory=list)
    current_best_variant: Optional[TradeVariant] = None
    market_context: Optional[Any] = None  # MarketContext — forward ref to avoid circular import
    conversation_history: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class TradeDecision(BaseModel):
    """A finalised, user-confirmed trade ready to be sent to MT5."""

    decision_id: str = Field(default_factory=_uuid4)
    draft_id: str
    symbol: str
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    risk_pct: float
    risk_reward_ratio: float
    rationale: str
    confirmed_at: datetime = Field(default_factory=_now)


class ExecutionResult(BaseModel):
    """The result of attempting to execute an order on MT5."""

    order_ticket: Optional[int] = None
    deal_id: Optional[int] = None
    symbol: str
    direction: TradeDirection
    requested_price: float
    fill_price: Optional[float] = None
    slippage: Optional[float] = None
    volume: float
    retcode: int
    retcode_description: str
    executed_at: datetime = Field(default_factory=_now)
    success: bool
