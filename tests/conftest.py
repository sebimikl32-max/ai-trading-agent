"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.schemas.market import MarketContext, MarketSnapshot, OHLCVBar, TickData, TechnicalFeatures
from src.schemas.mt5 import MT5SymbolInfo
from src.schemas.trade import (
    InterpretedTradeThesis,
    RawUserThesis,
    TradeDraft,
    TradeDirection,
    TradeVariant,
)
from src.services.debate_engine import DebateEngine
from src.services.intent_parser import IntentParser
from src.services.order_builder import OrderBuilder
from src.services.risk_manager import RiskManager
from src.services.trade_draft import TradeDraftManager


def _ts() -> datetime:
    return datetime.now(timezone.utc)


# ── Symbol info fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def eurusd_symbol_info() -> MT5SymbolInfo:
    return MT5SymbolInfo(
        name="EURUSD",
        digits=5,
        point=0.00001,
        trade_tick_size=0.00001,
        trade_tick_value=0.1,
        volume_min=0.01,
        volume_max=500.0,
        volume_step=0.01,
        trade_contract_size=100_000.0,
    )


@pytest.fixture
def xauusd_symbol_info() -> MT5SymbolInfo:
    return MT5SymbolInfo(
        name="XAUUSD",
        digits=2,
        point=0.01,
        trade_tick_size=0.01,
        trade_tick_value=1.0,
        volume_min=0.01,
        volume_max=50.0,
        volume_step=0.01,
        trade_contract_size=100.0,
    )


# ── Market data fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def sample_bars() -> list[OHLCVBar]:
    prices = [
        (1.0820, 1.0850, 1.0810, 1.0840),
        (1.0840, 1.0870, 1.0830, 1.0860),
        (1.0860, 1.0880, 1.0840, 1.0855),
        (1.0855, 1.0870, 1.0820, 1.0830),
        (1.0830, 1.0860, 1.0810, 1.0850),
        (1.0850, 1.0880, 1.0830, 1.0870),
        (1.0870, 1.0890, 1.0850, 1.0865),
        (1.0865, 1.0875, 1.0840, 1.0855),
        (1.0855, 1.0880, 1.0835, 1.0875),
        (1.0875, 1.0900, 1.0860, 1.0890),
        (1.0890, 1.0910, 1.0870, 1.0885),
        (1.0885, 1.0905, 1.0865, 1.0895),
        (1.0895, 1.0920, 1.0880, 1.0910),
        (1.0910, 1.0930, 1.0895, 1.0920),
        (1.0920, 1.0935, 1.0900, 1.0925),
    ]
    return [
        OHLCVBar(
            open=o, high=h, low=lo, close=c, volume=1000.0,
            timestamp=_ts(),
        )
        for o, h, lo, c in prices
    ]


@pytest.fixture
def sample_tick() -> TickData:
    return TickData(bid=1.0920, ask=1.0922, spread=0.00002)


@pytest.fixture
def sample_snapshot(sample_bars, sample_tick) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="EURUSD",
        tick=sample_tick,
        recent_bars=sample_bars,
        timeframe="H1",
    )


@pytest.fixture
def sample_market_context(sample_snapshot) -> MarketContext:
    features = TechnicalFeatures(
        atr_14=0.0010,
        rsi_14=55.0,
        sma_20=1.0870,
        sma_50=1.0850,
        recent_swing_high=1.0935,
        recent_swing_low=1.0810,
    )
    return MarketContext(
        symbol="EURUSD",
        snapshot=sample_snapshot,
        technical=features,
    )


# ── Trade draft fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def sample_thesis() -> InterpretedTradeThesis:
    return InterpretedTradeThesis(
        symbol="EURUSD",
        direction=TradeDirection.LONG,
        rationale="Bounce off key support",
        entry_price_hint=1.0920,
        stop_loss_hint=1.0880,
        take_profit_hint=1.1000,
        risk_pct_hint=1.0,
    )


@pytest.fixture
def sample_variant() -> TradeVariant:
    return TradeVariant(
        entry_price=1.0920,
        stop_loss=1.0880,
        take_profit=1.1000,
        lot_size=0.10,
        risk_pct=1.0,
        risk_reward_ratio=2.0,
        rationale="Bounce off key support",
        source="user",
    )


@pytest.fixture
def sample_draft(sample_thesis, sample_variant) -> TradeDraft:
    raw = RawUserThesis(raw_text="Long EURUSD at 1.0920, SL 1.0880, TP 1.1000", user_id="123")
    draft = TradeDraft(user_id="123", raw_thesis=raw)
    draft.interpreted_thesis = sample_thesis
    draft.variants = [sample_variant]
    draft.current_best_variant = sample_variant
    return draft


# ── Service fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(max_risk_pct=3.0, max_positions=5)


@pytest.fixture
def draft_manager() -> TradeDraftManager:
    return TradeDraftManager()


@pytest.fixture
def order_builder() -> OrderBuilder:
    return OrderBuilder(magic_number=234000)


@pytest.fixture
def intent_parser() -> IntentParser:
    return IntentParser(llm_engine=None)


@pytest.fixture
def debate_engine(risk_manager) -> DebateEngine:
    return DebateEngine(risk_manager=risk_manager, llm_engine=None)
