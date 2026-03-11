"""Debate engine — evaluate a trade draft, raise objections, suggest variants."""

from __future__ import annotations

import logging
from typing import Optional

from src.engines.llm_engine import LLMEngine
from src.schemas.market import MarketContext
from src.schemas.trade import (
    ObjectionCategory,
    ObjectionSeverity,
    TradeDraft,
    TradeObjection,
    TradeVariant,
)
from src.services.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class DebateEngine:
    """Debate engine implementing rule-based objection raising and variant generation.

    LLM is used to generate the final conversational narrative.
    All rule-based logic runs independently of the LLM so the engine is
    usable even when the LLM is unavailable.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        llm_engine: Optional[LLMEngine] = None,
    ) -> None:
        self._risk_manager = risk_manager
        self._llm = llm_engine

    async def evaluate_trade(
        self,
        draft: TradeDraft,
        market_context: Optional[MarketContext],
    ) -> tuple[list[TradeObjection], list[TradeVariant], str]:
        """Main evaluation entry-point.

        Returns:
            objections: list of TradeObjection raised
            alternative_variants: list of system-generated TradeVariant
            narrative: conversational string for the user
        """
        objections: list[TradeObjection] = []
        alternatives: list[TradeVariant] = []

        thesis = draft.interpreted_thesis
        variant = draft.current_best_variant

        if thesis is None:
            objections.append(
                TradeObjection(
                    severity=ObjectionSeverity.HIGH,
                    category=ObjectionCategory.GENERAL,
                    description="No interpreted thesis available. Cannot evaluate the trade.",
                    suggestion="Please provide more detail: symbol, direction, and rationale.",
                )
            )
            return objections, alternatives, self._fallback_narrative(objections, alternatives)

        if not thesis.rationale:
            objections.append(
                TradeObjection(
                    severity=ObjectionSeverity.MEDIUM,
                    category=ObjectionCategory.GENERAL,
                    description="No rationale provided. A weak thesis increases emotional trading risk.",
                    suggestion="Explain *why* you are taking this trade.",
                )
            )

        if variant:
            objections += self._check_variant(variant, market_context)
            alternatives += self._generate_alternatives(variant, market_context, thesis.symbol or "")

        narrative = await self._build_narrative(draft, objections, alternatives, market_context)
        return objections, alternatives, narrative

    # ── Rule-based checks ──────────────────────────────────────────────────────

    def _check_variant(
        self, variant: TradeVariant, ctx: Optional[MarketContext]
    ) -> list[TradeObjection]:
        objections: list[TradeObjection] = []
        rr = variant.risk_reward_ratio
        risk = variant.risk_pct

        # R:R checks
        if rr < 1.0:
            objections.append(
                TradeObjection(
                    severity=ObjectionSeverity.HIGH,
                    category=ObjectionCategory.RISK,
                    description=f"Risk:Reward ratio of {rr:.2f} is below 1:1. You risk more than you stand to gain.",
                    suggestion="Widen the take profit or tighten the stop loss to achieve at least 1:1.",
                )
            )
        elif rr < 1.5:
            objections.append(
                TradeObjection(
                    severity=ObjectionSeverity.MEDIUM,
                    category=ObjectionCategory.RISK,
                    description=f"Risk:Reward ratio of {rr:.2f} is below 1.5:1. Consider a better R:R.",
                    suggestion="Aim for at least 1.5:1 to maintain a positive expected value over many trades.",
                )
            )

        # Risk percent checks
        valid, reason = self._risk_manager.validate_risk(risk)
        if not valid:
            objections.append(
                TradeObjection(
                    severity=ObjectionSeverity.HIGH,
                    category=ObjectionCategory.SIZING,
                    description=reason,
                    suggestion=f"Reduce risk to below {self._risk_manager.max_risk_pct:.1f}%.",
                )
            )

        # ATR-based stop checks
        if ctx and ctx.technical.atr_14:
            atr = ctx.technical.atr_14
            sl_distance = abs(variant.entry_price - variant.stop_loss)
            if sl_distance < atr:
                objections.append(
                    TradeObjection(
                        severity=ObjectionSeverity.MEDIUM,
                        category=ObjectionCategory.TECHNICAL,
                        description=(
                            f"Stop loss distance ({sl_distance:.5f}) is less than 1× ATR ({atr:.5f}). "
                            "The stop may be too tight and at risk of being triggered by normal volatility."
                        ),
                        suggestion=f"Consider widening the stop to at least {atr:.5f} (1× ATR).",
                    )
                )
            elif sl_distance > 3 * atr:
                objections.append(
                    TradeObjection(
                        severity=ObjectionSeverity.MEDIUM,
                        category=ObjectionCategory.TECHNICAL,
                        description=(
                            f"Stop loss distance ({sl_distance:.5f}) is greater than 3× ATR ({atr:.5f}). "
                            "This is an unusually wide stop for current volatility."
                        ),
                        suggestion="Review whether a tighter stop near a key level would be more appropriate.",
                    )
                )

        return objections

    def _generate_alternatives(
        self,
        original: TradeVariant,
        ctx: Optional[MarketContext],
        symbol: str,
    ) -> list[TradeVariant]:
        alternatives: list[TradeVariant] = []
        if ctx is None or ctx.technical.atr_14 is None:
            return alternatives

        atr = ctx.technical.atr_14
        entry = original.entry_price
        is_long = original.take_profit > original.entry_price

        # ATR-based variant
        sl_atr = entry - atr if is_long else entry + atr
        tp_atr = entry + 2 * atr if is_long else entry - 2 * atr
        rr_atr = self._risk_manager.calculate_risk_reward(entry, sl_atr, tp_atr)
        alternatives.append(
            TradeVariant(
                entry_price=entry,
                stop_loss=round(sl_atr, 5),
                take_profit=round(tp_atr, 5),
                lot_size=original.lot_size,
                risk_pct=original.risk_pct,
                risk_reward_ratio=rr_atr,
                rationale=f"ATR-based: SL = 1× ATR ({atr:.5f}), TP = 2× ATR for 2:1 R:R",
                source="debate",
            )
        )

        # Swing-based variant if swing levels are available
        if ctx.technical.recent_swing_low and ctx.technical.recent_swing_high:
            if is_long:
                sl_swing = ctx.technical.recent_swing_low
                tp_swing = entry + 1.5 * abs(entry - sl_swing)
            else:
                sl_swing = ctx.technical.recent_swing_high
                tp_swing = entry - 1.5 * abs(sl_swing - entry)

            rr_swing = self._risk_manager.calculate_risk_reward(entry, sl_swing, tp_swing)
            alternatives.append(
                TradeVariant(
                    entry_price=entry,
                    stop_loss=round(sl_swing, 5),
                    take_profit=round(tp_swing, 5),
                    lot_size=original.lot_size,
                    risk_pct=original.risk_pct,
                    risk_reward_ratio=rr_swing,
                    rationale=(
                        f"Swing-based: SL below/above recent swing "
                        f"({'low' if is_long else 'high'} at {sl_swing:.5f})"
                    ),
                    source="debate",
                )
            )

        return alternatives

    # ── Narrative generation ───────────────────────────────────────────────────

    async def _build_narrative(
        self,
        draft: TradeDraft,
        objections: list[TradeObjection],
        alternatives: list[TradeVariant],
        ctx: Optional[MarketContext],
    ) -> str:
        if self._llm:
            try:
                from src.utils.formatting import format_trade_draft, format_market_summary

                draft_summary = format_trade_draft(draft)
                market_summary = format_market_summary(ctx) if ctx else "No market data available."
                obj_texts = [o.description for o in objections]
                var_texts = [
                    f"Entry {v.entry_price}, SL {v.stop_loss}, TP {v.take_profit} — {v.rationale}"
                    for v in alternatives
                ]
                return await self._llm.generate_debate_narrative(
                    draft_summary, obj_texts, var_texts, market_summary
                )
            except Exception as exc:
                logger.warning("LLM narrative generation failed: %s", exc)

        return self._fallback_narrative(objections, alternatives)

    @staticmethod
    def _fallback_narrative(
        objections: list[TradeObjection], alternatives: list[TradeVariant]
    ) -> str:
        lines = ["**Trade Debate Summary**\n"]
        if objections:
            lines.append("⚠️ *Concerns raised:*")
            for o in objections:
                lines.append(f"• [{o.severity.value}] {o.description}")
                if o.suggestion:
                    lines.append(f"  → Suggestion: {o.suggestion}")
        else:
            lines.append("✅ No major concerns identified.")

        if alternatives:
            lines.append("\n📐 *Alternative setups:*")
            for i, v in enumerate(alternatives, 1):
                lines.append(
                    f"{i}. Entry {v.entry_price} | SL {v.stop_loss} | TP {v.take_profit} "
                    f"| R:R {v.risk_reward_ratio:.2f} — {v.rationale}"
                )

        lines.append("\nReview the above and reply to refine, or /confirm to proceed.")
        return "\n".join(lines)
