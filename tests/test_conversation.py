"""Tests for ConversationManager — intake loop fixes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schemas.message import ConversationContext, ConversationState, ParsedMessage, UserIntent
from src.schemas.trade import InterpretedTradeThesis, RawUserThesis, TradeDraft, TradeDirection
from src.services.conversation import ConversationManager
from src.services.intent_parser import IntentParser
from src.services.trade_draft import TradeDraftManager


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_manager() -> ConversationManager:
    """Return a ConversationManager wired with stub collaborators."""
    intent_parser = IntentParser(llm_engine=None)
    draft_manager = TradeDraftManager()

    debate = MagicMock()
    debate.evaluate_trade = AsyncMock(return_value=([], [], "Debate narrative"))

    risk = MagicMock()
    risk.calculate_risk_reward = MagicMock(return_value=2.0)
    risk.calculate_lot_size = MagicMock(return_value=0.01)

    market = MagicMock()
    market.get_snapshot = AsyncMock(return_value=None)
    market.get_account_info = AsyncMock(return_value=None)
    market.get_symbol_info = AsyncMock(return_value=None)

    ta = MagicMock()
    ta.compute_features = MagicMock(return_value=None)

    order_builder = MagicMock()
    order_builder.build_market_order = MagicMock()
    order_builder.validate_order = MagicMock(return_value=(True, []))

    executor = MagicMock()
    executor.execute_order = AsyncMock(side_effect=RuntimeError("Not connected"))

    journal = MagicMock()
    journal.log_audit_event = AsyncMock(return_value=None)
    journal.create_entry = MagicMock(return_value=MagicMock())
    journal.save_entry = AsyncMock(return_value=None)

    return ConversationManager(
        intent_parser=intent_parser,
        draft_manager=draft_manager,
        debate_engine=debate,
        risk_manager=risk,
        market_data=market,
        ta_service=ta,
        order_builder=order_builder,
        mt5_executor=executor,
        journal_service=journal,
        llm_engine=None,
        allowed_user_ids=None,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestHandleIntakeDoesNotRestartDraft:
    """Bug 3: follow-up answers during INTAKE should enrich, not create a new draft."""

    @pytest.mark.asyncio
    async def test_direction_followup_enriches_not_restarts(self):
        """User says 'long' as a follow-up; should fill direction, not create new draft."""
        mgr = _make_manager()
        # Start a draft without a direction
        await mgr.handle_message("u1", "I want to trade gold, stop 2305, target 2360, entry 2320")
        ctx = mgr._contexts["u1"]
        assert ctx.state == ConversationState.AWAITING_CONFIRMATION or ctx.state in (
            ConversationState.INTAKE,
            ConversationState.DEBATING,
        )

        first_draft = ctx.active_draft
        # Simulate bot is in INTAKE with direction missing
        ctx.state = ConversationState.INTAKE
        thesis = ctx.active_draft.interpreted_thesis
        original_symbol = thesis.symbol

        # User replies just "long" — NEW_TRADE intent would fire
        await mgr.handle_message("u1", "long")

        # Should NOT have replaced the draft
        assert ctx.active_draft is first_draft or (
            ctx.active_draft is not None
            and ctx.active_draft.interpreted_thesis is not None
            and ctx.active_draft.interpreted_thesis.symbol == original_symbol
        )

    @pytest.mark.asyncio
    async def test_entry_followup_enriches_not_restarts(self):
        """User says 'entry at 2320' during intake; should add to existing draft."""
        mgr = _make_manager()
        # Start intake with symbol + direction but no entry
        reply = await mgr.handle_message("u1", "thinking of longing gold, stop 2305, target 2360")
        ctx = mgr._contexts["u1"]
        first_draft_id = ctx.active_draft.draft_id if ctx.active_draft else None

        ctx.state = ConversationState.INTAKE

        await mgr.handle_message("u1", "entry at 2320")

        # Draft should not have been replaced with a brand new one
        assert ctx.active_draft is not None
        assert ctx.active_draft.draft_id == first_draft_id


class TestEnrichDraftAllowsRefinement:
    """Bug 1: REFINE_TRADE intent should overwrite already-set fields."""

    @pytest.mark.asyncio
    async def test_refine_overwrites_stop_loss(self):
        """When intent is REFINE_TRADE, stop_loss_hint should be updated."""
        mgr = _make_manager()
        await mgr.handle_message("u1", "Long gold, entry 2320, stop 2305, target 2360, 1% risk")
        ctx = mgr._contexts["u1"]

        # Force INTAKE state and inject a thesis with stop_loss already set
        ctx.state = ConversationState.INTAKE
        thesis = ctx.active_draft.interpreted_thesis
        assert thesis is not None
        thesis.stop_loss_hint = 2305.0

        # Now the user refines — "change my stop to 2310"
        await mgr.handle_message("u1", "change my stop to 2310")

        updated_thesis = ctx.active_draft.interpreted_thesis
        assert updated_thesis.stop_loss_hint == pytest.approx(2310.0)

    @pytest.mark.asyncio
    async def test_enrich_does_not_overwrite_existing_symbol(self):
        """Normal enrichment (non-REFINE) should not overwrite an already-set symbol."""
        mgr = _make_manager()
        await mgr.handle_message("u1", "Long gold, stop 2305, target 2360, entry 2320")
        ctx = mgr._contexts["u1"]
        ctx.state = ConversationState.INTAKE

        thesis = ctx.active_draft.interpreted_thesis
        thesis.symbol = "XAUUSD"
        thesis.direction = TradeDirection.LONG

        # Send a message that would extract a different symbol only if overwrite is allowed
        # GENERAL_CHAT with just a risk pct — symbol should not be overwritten
        await mgr.handle_message("u1", "use 2% risk")

        assert ctx.active_draft.interpreted_thesis.symbol == "XAUUSD"


class TestBareNumberContextAssignment:
    """Bug 4: A bare number reply should fill the first missing price field."""

    @pytest.mark.asyncio
    async def test_bare_number_fills_entry_first(self):
        """If entry is missing, bare number should fill entry_price_hint."""
        mgr = _make_manager()
        await mgr.handle_message("u1", "Long EURUSD, stop 1.0880, target 1.1000")
        ctx = mgr._contexts["u1"]
        ctx.state = ConversationState.INTAKE

        # Ensure entry is not set
        thesis = ctx.active_draft.interpreted_thesis
        thesis.entry_price_hint = None

        await mgr.handle_message("u1", "1.0920")

        assert ctx.active_draft.interpreted_thesis.entry_price_hint == pytest.approx(1.092)

    @pytest.mark.asyncio
    async def test_bare_number_fills_stop_when_entry_set(self):
        """If entry is set but stop is missing, bare number should fill stop_loss_hint."""
        mgr = _make_manager()
        await mgr.handle_message("u1", "Long EURUSD, entry 1.0920, target 1.1000")
        ctx = mgr._contexts["u1"]
        ctx.state = ConversationState.INTAKE

        thesis = ctx.active_draft.interpreted_thesis
        thesis.entry_price_hint = 1.092
        thesis.stop_loss_hint = None

        await mgr.handle_message("u1", "1.0880")

        assert ctx.active_draft.interpreted_thesis.stop_loss_hint == pytest.approx(1.088)

    @pytest.mark.asyncio
    async def test_bare_number_fills_tp_when_entry_and_stop_set(self):
        """If entry and stop are set but tp is missing, bare number fills take_profit_hint."""
        mgr = _make_manager()
        await mgr.handle_message("u1", "Long EURUSD, entry 1.0920, stop 1.0880")
        ctx = mgr._contexts["u1"]
        ctx.state = ConversationState.INTAKE

        thesis = ctx.active_draft.interpreted_thesis
        thesis.entry_price_hint = 1.092
        thesis.stop_loss_hint = 1.088
        thesis.take_profit_hint = None

        await mgr.handle_message("u1", "1.1000")

        assert ctx.active_draft.interpreted_thesis.take_profit_hint == pytest.approx(1.1)
