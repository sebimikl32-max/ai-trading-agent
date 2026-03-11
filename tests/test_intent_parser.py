"""Tests for IntentParser."""

from __future__ import annotations

import pytest

from src.schemas.message import UserIntent
from src.schemas.trade import TradeDirection
from src.services.intent_parser import IntentParser, _canonicalise


class TestSymbolExtraction:
    @pytest.mark.asyncio
    async def test_gold_slang(self, intent_parser):
        result = await intent_parser.parse("I want to long gold here", "u1")
        assert result.extracted_symbol == "XAUUSD"

    @pytest.mark.asyncio
    async def test_cable_slang(self, intent_parser):
        result = await intent_parser.parse("Short cable at 1.27", "u1")
        assert result.extracted_symbol == "GBPUSD"

    @pytest.mark.asyncio
    async def test_fiber_slang(self, intent_parser):
        result = await intent_parser.parse("Fiber rejecting resistance", "u1")
        assert result.extracted_symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_nas_slang(self, intent_parser):
        result = await intent_parser.parse("Short nas at the highs", "u1")
        assert result.extracted_symbol == "NAS100"

    @pytest.mark.asyncio
    async def test_btc_slang(self, intent_parser):
        result = await intent_parser.parse("Buy btc dip", "u1")
        assert result.extracted_symbol == "BTCUSD"

    @pytest.mark.asyncio
    async def test_oil_slang(self, intent_parser):
        result = await intent_parser.parse("Long oil at 80", "u1")
        assert result.extracted_symbol == "USOIL"

    @pytest.mark.asyncio
    async def test_explicit_symbol(self, intent_parser):
        result = await intent_parser.parse("Buy EURUSD at 1.09", "u1")
        assert result.extracted_symbol == "EURUSD"


class TestDirectionExtraction:
    @pytest.mark.asyncio
    async def test_long(self, intent_parser):
        result = await intent_parser.parse("Long EURUSD", "u1")
        assert result.extracted_direction == TradeDirection.LONG

    @pytest.mark.asyncio
    async def test_short(self, intent_parser):
        result = await intent_parser.parse("Short gold at 2300", "u1")
        assert result.extracted_direction == TradeDirection.SHORT

    @pytest.mark.asyncio
    async def test_buy(self, intent_parser):
        result = await intent_parser.parse("Buy GBPUSD", "u1")
        assert result.extracted_direction == TradeDirection.LONG

    @pytest.mark.asyncio
    async def test_sell(self, intent_parser):
        result = await intent_parser.parse("Sell USDJPY now", "u1")
        assert result.extracted_direction == TradeDirection.SHORT

    @pytest.mark.asyncio
    async def test_bearish(self, intent_parser):
        result = await intent_parser.parse("Bearish on the euro", "u1")
        assert result.extracted_direction == TradeDirection.SHORT


class TestIntentClassification:
    @pytest.mark.asyncio
    async def test_new_trade(self, intent_parser):
        result = await intent_parser.parse("Thinking of longing gold here", "u1")
        assert result.intent == UserIntent.NEW_TRADE

    @pytest.mark.asyncio
    async def test_confirm(self, intent_parser):
        result = await intent_parser.parse("Yes, confirm the trade", "u1")
        assert result.intent == UserIntent.CONFIRM_TRADE

    @pytest.mark.asyncio
    async def test_reject(self, intent_parser):
        result = await intent_parser.parse("No, reject it", "u1")
        assert result.intent == UserIntent.REJECT_TRADE

    @pytest.mark.asyncio
    async def test_cancel(self, intent_parser):
        result = await intent_parser.parse("Cancel everything", "u1")
        assert result.intent == UserIntent.CANCEL

    @pytest.mark.asyncio
    async def test_question(self, intent_parser):
        result = await intent_parser.parse("What is a good stop loss here?", "u1")
        assert result.intent == UserIntent.ASK_QUESTION

    @pytest.mark.asyncio
    async def test_analysis(self, intent_parser):
        result = await intent_parser.parse("Analyse XAUUSD for me", "u1")
        assert result.intent == UserIntent.REQUEST_ANALYSIS


class TestPriceLevelExtraction:
    @pytest.mark.asyncio
    async def test_entry_extraction(self, intent_parser):
        result = await intent_parser.parse("Entry at 1.09200", "u1")
        assert "entry_price" in result.extracted_price_levels
        assert result.extracted_price_levels["entry_price"] == pytest.approx(1.092)

    @pytest.mark.asyncio
    async def test_stop_loss_extraction(self, intent_parser):
        result = await intent_parser.parse("Stop loss at 1.0880", "u1")
        assert "stop_loss" in result.extracted_price_levels

    @pytest.mark.asyncio
    async def test_take_profit_extraction(self, intent_parser):
        result = await intent_parser.parse("TP at 1.1000", "u1")
        assert "take_profit" in result.extracted_price_levels

    @pytest.mark.asyncio
    async def test_risk_pct_extraction(self, intent_parser):
        result = await intent_parser.parse("Use 1.5% risk on this", "u1")
        assert result.extracted_risk_pct == pytest.approx(1.5)


class TestCanonicalise:
    def test_gold(self):
        assert _canonicalise("gold") == "XAUUSD"

    def test_cable(self):
        assert _canonicalise("cable") == "GBPUSD"

    def test_unknown_passed_through_uppercased(self):
        assert _canonicalise("EURUSD") == "EURUSD"

    def test_none_returns_none(self):
        assert _canonicalise(None) is None
