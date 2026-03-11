"""Protocol interfaces for all major services.

Defining behaviour through Protocols (structural subtyping) means future
implementations — ML models, alternative brokers, macro data sources, etc. —
can be swapped in without touching the rest of the codebase.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from src.schemas.market import MarketContext, MarketSnapshot, TechnicalFeatures
from src.schemas.message import ParsedMessage
from src.schemas.mt5 import MT5AccountInfo, MT5OrderRequest, MT5OrderResponse, MT5SymbolInfo
from src.schemas.trade import (
    ExecutionResult,
    TradeDraft,
    TradeObjection,
    TradeVariant,
)


@runtime_checkable
class IntentParserProtocol(Protocol):
    async def parse(self, text: str, user_id: str) -> ParsedMessage:
        ...


@runtime_checkable
class MarketDataProtocol(Protocol):
    async def get_snapshot(self, symbol: str, timeframe: str, bars: int) -> MarketSnapshot:
        ...

    async def get_symbol_info(self, symbol: str) -> MT5SymbolInfo:
        ...

    async def get_account_info(self) -> MT5AccountInfo:
        ...


@runtime_checkable
class TechnicalAnalysisProtocol(Protocol):
    def compute_features(self, snapshot: MarketSnapshot) -> TechnicalFeatures:
        ...


@runtime_checkable
class RiskManagerProtocol(Protocol):
    def calculate_lot_size(
        self,
        account_balance: float,
        risk_pct: float,
        entry: float,
        stop_loss: float,
        symbol_info: MT5SymbolInfo,
    ) -> float:
        ...

    def calculate_risk_reward(
        self, entry: float, stop_loss: float, take_profit: float
    ) -> float:
        ...


@runtime_checkable
class DebateEngineProtocol(Protocol):
    async def evaluate_trade(
        self,
        draft: TradeDraft,
        market_context: Optional[MarketContext],
    ) -> tuple[list[TradeObjection], list[TradeVariant], str]:
        ...


@runtime_checkable
class ExecutorProtocol(Protocol):
    async def execute_order(self, request: MT5OrderRequest) -> MT5OrderResponse:
        ...

    async def check_connection(self) -> bool:
        ...


# ── Phase 2+ extension points — stubs for future implementations ──────────────


@runtime_checkable
class MacroDataProtocol(Protocol):
    """Phase 2: Fetch and interpret macro-economic data (CPI, rates, calendar)."""

    async def get_macro_context(self, symbol: str) -> dict[str, Any]:
        ...


@runtime_checkable
class PatternRecognitionProtocol(Protocol):
    """Phase 3: Detect chart patterns from OHLCV data."""

    async def detect_patterns(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        ...


@runtime_checkable
class BehaviourAnalysisProtocol(Protocol):
    """Phase 4: Analyse user behaviour and flag emotional trading patterns."""

    async def assess_user_state(self, user_id: str, recent_messages: list[str]) -> dict[str, Any]:
        ...


@runtime_checkable
class RegimeClassifierProtocol(Protocol):
    """Phase 4: Classify market regime (trending, ranging, volatile)."""

    async def classify_regime(self, context: MarketContext) -> str:
        ...
