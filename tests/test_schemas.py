"""Tests for Pydantic v2 schemas."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.schemas.journal import AuditLogEntry, JournalEntry
from src.schemas.market import MarketContext, MarketSnapshot, OHLCVBar, TickData, TechnicalFeatures
from src.schemas.message import ConversationContext, ParsedMessage, UserIntent
from src.schemas.mt5 import MT5AccountInfo, MT5OrderRequest, MT5OrderResponse, MT5SymbolInfo
from src.schemas.trade import (
    ExecutionResult,
    InterpretedTradeThesis,
    ObjectionCategory,
    ObjectionSeverity,
    RawUserThesis,
    TradeDraft,
    TradeDecision,
    TradeDirection,
    TradeObjection,
    TradeStatus,
    TradeVariant,
)


class TestTradeSchemas:
    def test_raw_user_thesis_defaults(self):
        thesis = RawUserThesis(raw_text="long gold", user_id="42")
        assert thesis.raw_text == "long gold"
        assert thesis.user_id == "42"
        assert isinstance(thesis.timestamp, datetime)

    def test_interpreted_trade_thesis_optional_fields(self):
        thesis = InterpretedTradeThesis(symbol="XAUUSD", direction=TradeDirection.LONG)
        assert thesis.symbol == "XAUUSD"
        assert thesis.direction == TradeDirection.LONG
        assert thesis.rationale is None
        assert thesis.entry_price_hint is None

    def test_trade_variant_uuid_default(self):
        v = TradeVariant(
            entry_price=1.09,
            stop_loss=1.08,
            take_profit=1.11,
            lot_size=0.1,
            risk_pct=1.0,
            risk_reward_ratio=2.0,
            rationale="Test",
            source="user",
        )
        assert len(v.variant_id) == 36  # UUID4 length
        assert v.estimated_profit is None

    def test_trade_objection_fields(self):
        obj = TradeObjection(
            severity=ObjectionSeverity.HIGH,
            category=ObjectionCategory.RISK,
            description="R:R too low",
            suggestion="Widen TP",
        )
        assert obj.severity == ObjectionSeverity.HIGH
        assert obj.suggestion == "Widen TP"
        assert len(obj.objection_id) == 36

    def test_trade_draft_defaults(self):
        thesis = RawUserThesis(raw_text="test", user_id="1")
        draft = TradeDraft(user_id="1", raw_thesis=thesis)
        assert draft.status == TradeStatus.INTAKE
        assert draft.variants == []
        assert draft.objections == []
        assert draft.current_best_variant is None

    def test_trade_decision_fields(self):
        d = TradeDecision(
            draft_id="abc",
            symbol="EURUSD",
            direction=TradeDirection.SHORT,
            entry_price=1.09,
            stop_loss=1.10,
            take_profit=1.07,
            lot_size=0.1,
            risk_pct=1.0,
            risk_reward_ratio=2.0,
            rationale="Breakdown",
        )
        assert d.direction == TradeDirection.SHORT
        assert d.symbol == "EURUSD"

    def test_execution_result(self):
        r = ExecutionResult(
            symbol="XAUUSD",
            direction=TradeDirection.LONG,
            requested_price=2300.0,
            volume=0.1,
            retcode=10009,
            retcode_description="Done",
            success=True,
        )
        assert r.success is True
        assert r.slippage is None


class TestMarketSchemas:
    def test_tick_data(self):
        tick = TickData(bid=1.092, ask=1.0922, spread=0.0002)
        assert tick.spread == pytest.approx(0.0002)

    def test_ohlcv_bar(self):
        bar = OHLCVBar(
            open=1.09, high=1.10, low=1.08, close=1.095,
            volume=1000.0, timestamp=datetime.now(timezone.utc)
        )
        assert bar.close == 1.095

    def test_technical_features_all_optional(self):
        feat = TechnicalFeatures()
        assert feat.atr_14 is None
        assert feat.rsi_14 is None

    def test_market_context_phase2_hooks(self):
        ctx = MarketContext(
            symbol="XAUUSD",
            snapshot=MarketSnapshot(
                symbol="XAUUSD",
                tick=TickData(bid=2300.0, ask=2300.5, spread=0.5),
                recent_bars=[],
                timeframe="H1",
            ),
            technical=TechnicalFeatures(),
        )
        assert ctx.macro_context is None
        assert ctx.sentiment_context is None
        assert ctx.regime_label is None


class TestMessageSchemas:
    def test_parsed_message_confidence_bounds(self):
        msg = ParsedMessage(intent=UserIntent.NEW_TRADE, raw_text="long gold", confidence=0.8)
        assert msg.confidence == 0.8

    def test_parsed_message_invalid_confidence(self):
        with pytest.raises(Exception):
            ParsedMessage(intent=UserIntent.NEW_TRADE, raw_text="x", confidence=1.5)

    def test_conversation_context_defaults(self):
        from src.schemas.message import ConversationState
        ctx = ConversationContext(user_id="99")
        assert ctx.state == ConversationState.IDLE
        assert ctx.active_draft is None
        assert ctx.message_history == []


class TestMT5Schemas:
    def test_mt5_order_request_defaults(self):
        req = MT5OrderRequest(
            action=1, symbol="EURUSD", volume=0.1, type=0,
            price=1.09, sl=1.08, tp=1.11,
        )
        assert req.deviation == 20
        assert req.magic == 234000
        assert req.comment == "ai-trading-agent"

    def test_mt5_symbol_info(self, eurusd_symbol_info):
        assert eurusd_symbol_info.point == pytest.approx(0.00001)
        assert eurusd_symbol_info.volume_step == pytest.approx(0.01)

    def test_mt5_account_info(self):
        acc = MT5AccountInfo(
            login=12345, balance=10000.0, equity=10050.0,
            margin=500.0, free_margin=9550.0, leverage=100,
            currency="USD", server="Demo-Server",
        )
        assert acc.balance == 10000.0


class TestJournalSchemas:
    def test_journal_entry_creation(self, sample_draft):
        entry = JournalEntry(
            trade_id=sample_draft.draft_id,
            user_id=sample_draft.user_id,
            raw_thesis=sample_draft.raw_thesis,
        )
        assert entry.outcome_pips is None
        assert entry.tags == []
        assert entry.notes == ""
        assert entry.strategy_label is None

    def test_audit_log_entry(self):
        log = AuditLogEntry(
            event_type="trade_confirmed",
            actor="user",
            details={"draft_id": "abc123"},
        )
        assert log.actor == "user"
        assert log.trade_id is None
        assert isinstance(log.log_id, str)
