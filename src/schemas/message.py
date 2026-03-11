"""Messaging / conversation schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.schemas.trade import TradeDraft, TradeDirection


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Intent classification ─────────────────────────────────────────────────────


class UserIntent(str, Enum):
    NEW_TRADE = "NEW_TRADE"
    REFINE_TRADE = "REFINE_TRADE"
    ASK_QUESTION = "ASK_QUESTION"
    CONFIRM_TRADE = "CONFIRM_TRADE"
    REJECT_TRADE = "REJECT_TRADE"
    CANCEL = "CANCEL"
    GENERAL_CHAT = "GENERAL_CHAT"
    REQUEST_ANALYSIS = "REQUEST_ANALYSIS"


class ParsedMessage(BaseModel):
    """Result of parsing a raw user message."""

    intent: UserIntent
    extracted_symbol: Optional[str] = None
    extracted_direction: Optional[TradeDirection] = None
    extracted_price_levels: dict[str, float] = Field(default_factory=dict)
    extracted_risk_pct: Optional[float] = None
    raw_text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


# ── Conversation state machine ────────────────────────────────────────────────


class ConversationState(str, Enum):
    IDLE = "IDLE"
    INTAKE = "INTAKE"
    DEBATING = "DEBATING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTED = "EXECUTED"


class ConversationContext(BaseModel):
    """Per-user conversation state, persisted in memory during a session."""

    user_id: str
    state: ConversationState = ConversationState.IDLE
    active_draft: Optional[TradeDraft] = None
    message_history: list[dict] = Field(default_factory=list)
    last_activity: datetime = Field(default_factory=_now)
