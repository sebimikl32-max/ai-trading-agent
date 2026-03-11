"""Tests for OrderBuilder."""

from __future__ import annotations

import pytest

from src.schemas.trade import TradeDecision, TradeDirection
from src.services.order_builder import OrderBuilder


def _make_decision(
    direction: TradeDirection = TradeDirection.LONG,
    entry: float = 1.0920,
    sl: float = 1.0880,
    tp: float = 1.1000,
    lots: float = 0.10,
) -> TradeDecision:
    return TradeDecision(
        draft_id="test-draft",
        symbol="EURUSD",
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        lot_size=lots,
        risk_pct=1.0,
        risk_reward_ratio=2.0,
        rationale="Test rationale",
    )


class TestBuildMarketOrder:
    def test_long_order_type(self, order_builder):
        decision = _make_decision(TradeDirection.LONG)
        request = order_builder.build_market_order(decision)
        assert request.type == 0  # ORDER_TYPE_BUY
        assert request.symbol == "EURUSD"
        assert request.volume == pytest.approx(0.10)
        assert request.price == pytest.approx(1.0920)
        assert request.sl == pytest.approx(1.0880)
        assert request.tp == pytest.approx(1.1000)

    def test_short_order_type(self, order_builder):
        decision = _make_decision(
            TradeDirection.SHORT, entry=1.09, sl=1.10, tp=1.07
        )
        request = order_builder.build_market_order(decision)
        assert request.type == 1  # ORDER_TYPE_SELL

    def test_magic_number_set(self, order_builder):
        decision = _make_decision()
        request = order_builder.build_market_order(decision)
        assert request.magic == 234000

    def test_comment_includes_decision_id(self, order_builder):
        decision = _make_decision()
        request = order_builder.build_market_order(decision)
        assert "ai-agent:" in request.comment


class TestValidateOrder:
    def test_valid_long_order(self, order_builder):
        decision = _make_decision(TradeDirection.LONG, entry=1.09, sl=1.08, tp=1.11)
        request = order_builder.build_market_order(decision)
        valid, errors = order_builder.validate_order(request)
        assert valid is True
        assert errors == []

    def test_valid_short_order(self, order_builder):
        decision = _make_decision(TradeDirection.SHORT, entry=1.09, sl=1.10, tp=1.07)
        request = order_builder.build_market_order(decision)
        valid, errors = order_builder.validate_order(request)
        assert valid is True
        assert errors == []

    def test_long_sl_above_entry_is_invalid(self, order_builder):
        decision = _make_decision(TradeDirection.LONG, entry=1.09, sl=1.10, tp=1.11)
        request = order_builder.build_market_order(decision)
        valid, errors = order_builder.validate_order(request)
        assert valid is False
        assert any("stop loss" in e.lower() for e in errors)

    def test_long_tp_below_entry_is_invalid(self, order_builder):
        decision = _make_decision(TradeDirection.LONG, entry=1.09, sl=1.08, tp=1.07)
        request = order_builder.build_market_order(decision)
        valid, errors = order_builder.validate_order(request)
        assert valid is False
        assert any("take profit" in e.lower() for e in errors)

    def test_short_sl_below_entry_is_invalid(self, order_builder):
        decision = _make_decision(TradeDirection.SHORT, entry=1.09, sl=1.08, tp=1.07)
        request = order_builder.build_market_order(decision)
        valid, errors = order_builder.validate_order(request)
        assert valid is False

    def test_zero_volume_invalid(self, order_builder):
        decision = _make_decision(lots=0.0)
        request = order_builder.build_market_order(decision)
        request.volume = 0.0
        valid, errors = order_builder.validate_order(request)
        assert valid is False
        assert any("volume" in e.lower() for e in errors)

    def test_empty_symbol_invalid(self, order_builder):
        decision = _make_decision()
        request = order_builder.build_market_order(decision)
        request.symbol = ""
        valid, errors = order_builder.validate_order(request)
        assert valid is False


class TestToMT5Dict:
    def test_returns_dict(self, order_builder):
        decision = _make_decision()
        request = order_builder.build_market_order(decision)
        d = order_builder.to_mt5_dict(request)
        assert isinstance(d, dict)
        assert "symbol" in d
        assert "volume" in d
        assert "price" in d
        assert "sl" in d
        assert "tp" in d
