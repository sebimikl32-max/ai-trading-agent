"""Market data and technical analysis Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Raw market data ───────────────────────────────────────────────────────────


class TickData(BaseModel):
    bid: float
    ask: float
    spread: float
    last: Optional[float] = None
    volume: Optional[float] = None
    timestamp: datetime = Field(default_factory=_now)


class OHLCVBar(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime


class MarketSnapshot(BaseModel):
    symbol: str
    tick: TickData
    recent_bars: list[OHLCVBar]
    timeframe: str  # e.g. "H1", "D1"


# ── Derived / computed features ───────────────────────────────────────────────


class TechnicalFeatures(BaseModel):
    """Computed technical indicators used during the debate phase."""

    atr_14: Optional[float] = None
    rsi_14: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    recent_swing_high: Optional[float] = None
    recent_swing_low: Optional[float] = None
    daily_range: Optional[float] = None
    current_spread: Optional[float] = None
    volatility_percentile: Optional[float] = None


# ── Composite market context ──────────────────────────────────────────────────


class MarketContext(BaseModel):
    """Full market snapshot plus derived features for a given symbol."""

    symbol: str
    snapshot: MarketSnapshot
    technical: TechnicalFeatures
    retrieved_at: datetime = Field(default_factory=_now)
    # Phase 2+ hooks — present but unpopulated in Phase 1
    macro_context: Optional[dict] = None
    sentiment_context: Optional[dict] = None
    regime_label: Optional[str] = None
