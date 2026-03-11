"""Tests for TradeDraftManager."""

from __future__ import annotations

import pytest

from src.schemas.trade import (
    InterpretedTradeThesis,
    ObjectionCategory,
    ObjectionSeverity,
    TradeDirection,
    TradeObjection,
    TradeStatus,
    TradeVariant,
)
from src.services.trade_draft import TradeDraftManager


class TestCreateDraft:
    def test_basic_creation(self, draft_manager):
        draft = draft_manager.create_draft("user1", "long EURUSD")
        assert draft.user_id == "user1"
        assert draft.raw_thesis.raw_text == "long EURUSD"
        assert draft.status == TradeStatus.INTAKE
        assert draft.variants == []
        assert draft.objections == []

    def test_unique_ids(self, draft_manager):
        d1 = draft_manager.create_draft("u1", "long gold")
        d2 = draft_manager.create_draft("u1", "short cable")
        assert d1.draft_id != d2.draft_id


class TestUpdateDraft:
    def test_update_thesis(self, draft_manager):
        draft = draft_manager.create_draft("u1", "long EURUSD")
        thesis = InterpretedTradeThesis(symbol="EURUSD", direction=TradeDirection.LONG)
        updated = draft_manager.update_draft(draft, thesis)
        assert updated.interpreted_thesis.symbol == "EURUSD"
        assert updated.interpreted_thesis.direction == TradeDirection.LONG


class TestAddVariant:
    def test_add_variant(self, draft_manager, sample_variant):
        draft = draft_manager.create_draft("u1", "test")
        draft_manager.add_variant(draft, sample_variant)
        assert len(draft.variants) == 1
        assert draft.variants[0].entry_price == 1.0920

    def test_add_multiple_variants(self, draft_manager, sample_variant):
        draft = draft_manager.create_draft("u1", "test")
        v2 = TradeVariant(
            entry_price=1.0925,
            stop_loss=1.0885,
            take_profit=1.1005,
            lot_size=0.08,
            risk_pct=1.0,
            risk_reward_ratio=2.0,
            rationale="Variant 2",
            source="debate",
        )
        draft_manager.add_variant(draft, sample_variant)
        draft_manager.add_variant(draft, v2)
        assert len(draft.variants) == 2


class TestAddObjection:
    def test_add_objection(self, draft_manager):
        draft = draft_manager.create_draft("u1", "test")
        obj = TradeObjection(
            severity=ObjectionSeverity.HIGH,
            category=ObjectionCategory.RISK,
            description="R:R too low",
        )
        draft_manager.add_objection(draft, obj)
        assert len(draft.objections) == 1


class TestIsComplete:
    def test_complete_draft(self, draft_manager, sample_draft):
        complete, missing = draft_manager.is_complete(sample_draft)
        assert complete is True
        assert missing == []

    def test_missing_symbol(self, draft_manager, sample_draft):
        sample_draft.interpreted_thesis.symbol = None
        complete, missing = draft_manager.is_complete(sample_draft)
        assert complete is False
        assert "symbol" in missing

    def test_missing_direction(self, draft_manager, sample_draft):
        sample_draft.interpreted_thesis.direction = None
        complete, missing = draft_manager.is_complete(sample_draft)
        assert complete is False
        assert "direction" in missing

    def test_missing_variant(self, draft_manager, sample_draft):
        sample_draft.current_best_variant = None
        complete, missing = draft_manager.is_complete(sample_draft)
        assert complete is False
        assert "current_best_variant" in missing

    def test_no_thesis(self, draft_manager):
        draft = draft_manager.create_draft("u1", "test")
        complete, missing = draft_manager.is_complete(draft)
        assert complete is False
        assert "interpreted_thesis" in missing


class TestToDecision:
    def test_converts_complete_draft(self, draft_manager, sample_draft):
        decision = draft_manager.to_decision(sample_draft)
        assert decision.symbol == "EURUSD"
        assert decision.direction == TradeDirection.LONG
        assert decision.entry_price == 1.0920
        assert decision.stop_loss == 1.0880
        assert decision.take_profit == 1.1000
        assert decision.draft_id == sample_draft.draft_id

    def test_raises_on_incomplete_draft(self, draft_manager):
        draft = draft_manager.create_draft("u1", "test")
        with pytest.raises(ValueError):
            draft_manager.to_decision(draft)


class TestTransitionStatus:
    def test_status_transitions(self, draft_manager):
        draft = draft_manager.create_draft("u1", "test")
        assert draft.status == TradeStatus.INTAKE
        draft_manager.transition_status(draft, TradeStatus.DEBATING)
        assert draft.status == TradeStatus.DEBATING
        draft_manager.transition_status(draft, TradeStatus.CONFIRMED)
        assert draft.status == TradeStatus.CONFIRMED
