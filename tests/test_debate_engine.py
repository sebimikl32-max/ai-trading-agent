"""Tests for DebateEngine."""

from __future__ import annotations

import pytest

from src.schemas.market import MarketContext, MarketSnapshot, TechnicalFeatures, TickData
from src.schemas.trade import ObjectionSeverity, TradeVariant
from src.services.debate_engine import DebateEngine
from src.services.risk_manager import RiskManager


@pytest.fixture
def debate_engine_no_llm():
    rm = RiskManager(max_risk_pct=3.0, max_positions=5)
    return DebateEngine(risk_manager=rm, llm_engine=None)


@pytest.fixture
def market_ctx_with_atr(sample_market_context):
    return sample_market_context


class TestEvaluateTrade:
    @pytest.mark.asyncio
    async def test_no_thesis_returns_objection(self, debate_engine_no_llm):
        from src.services.trade_draft import TradeDraftManager
        dm = TradeDraftManager()
        draft = dm.create_draft("u1", "vague idea")
        objections, variants, narrative = await debate_engine_no_llm.evaluate_trade(draft, None)
        assert len(objections) >= 1
        assert any(o.severity == ObjectionSeverity.HIGH for o in objections)

    @pytest.mark.asyncio
    async def test_good_rr_no_major_objections(self, debate_engine_no_llm, sample_draft):
        # R:R = 2.0, risk = 1% — should be clean
        objections, variants, narrative = await debate_engine_no_llm.evaluate_trade(
            sample_draft, None
        )
        rr_objections = [
            o for o in objections
            if o.severity in (ObjectionSeverity.HIGH, ObjectionSeverity.CRITICAL)
            and "ratio" in o.description.lower()
        ]
        assert rr_objections == []

    @pytest.mark.asyncio
    async def test_low_rr_generates_objection(self, debate_engine_no_llm, sample_draft):
        # Override variant with poor R:R
        sample_draft.current_best_variant.risk_reward_ratio = 0.8
        sample_draft.current_best_variant.take_profit = 1.0952  # small TP
        objections, _, _ = await debate_engine_no_llm.evaluate_trade(sample_draft, None)
        rr_objections = [o for o in objections if "ratio" in o.description.lower()]
        assert len(rr_objections) >= 1

    @pytest.mark.asyncio
    async def test_high_risk_generates_objection(self, debate_engine_no_llm, sample_draft):
        sample_draft.current_best_variant.risk_pct = 5.0  # above max_risk_pct of 3.0
        objections, _, _ = await debate_engine_no_llm.evaluate_trade(sample_draft, None)
        risk_objections = [o for o in objections if "risk" in o.description.lower()]
        assert len(risk_objections) >= 1

    @pytest.mark.asyncio
    async def test_tight_sl_generates_objection(
        self, debate_engine_no_llm, sample_draft, market_ctx_with_atr
    ):
        # ATR = 0.0010; set SL distance to 0.0005 (< ATR)
        sample_draft.current_best_variant.stop_loss = 1.0915  # only 5 pips from entry
        objections, _, _ = await debate_engine_no_llm.evaluate_trade(
            sample_draft, market_ctx_with_atr
        )
        tight_objections = [o for o in objections if "tight" in o.description.lower()]
        assert len(tight_objections) >= 1

    @pytest.mark.asyncio
    async def test_atr_variants_generated_with_market_ctx(
        self, debate_engine_no_llm, sample_draft, market_ctx_with_atr
    ):
        _, alternatives, _ = await debate_engine_no_llm.evaluate_trade(
            sample_draft, market_ctx_with_atr
        )
        atr_variants = [v for v in alternatives if "ATR" in v.rationale]
        assert len(atr_variants) >= 1

    @pytest.mark.asyncio
    async def test_swing_variants_generated_with_swing_levels(
        self, debate_engine_no_llm, sample_draft, market_ctx_with_atr
    ):
        _, alternatives, _ = await debate_engine_no_llm.evaluate_trade(
            sample_draft, market_ctx_with_atr
        )
        swing_variants = [v for v in alternatives if "Swing" in v.rationale]
        assert len(swing_variants) >= 1

    @pytest.mark.asyncio
    async def test_no_market_ctx_no_alternatives(self, debate_engine_no_llm, sample_draft):
        _, alternatives, _ = await debate_engine_no_llm.evaluate_trade(sample_draft, None)
        assert alternatives == []

    @pytest.mark.asyncio
    async def test_narrative_is_non_empty_string(
        self, debate_engine_no_llm, sample_draft
    ):
        _, _, narrative = await debate_engine_no_llm.evaluate_trade(sample_draft, None)
        assert isinstance(narrative, str)
        assert len(narrative) > 10

    @pytest.mark.asyncio
    async def test_missing_rationale_generates_objection(
        self, debate_engine_no_llm, sample_draft
    ):
        sample_draft.interpreted_thesis.rationale = None
        objections, _, _ = await debate_engine_no_llm.evaluate_trade(sample_draft, None)
        rationale_objections = [o for o in objections if "rationale" in o.description.lower()]
        assert len(rationale_objections) >= 1
