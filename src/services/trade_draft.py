"""Trade draft manager — create, update, and finalise TradeDraft objects."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.schemas.trade import (
    InterpretedTradeThesis,
    RawUserThesis,
    TradeDraft,
    TradeDecision,
    TradeObjection,
    TradeStatus,
    TradeVariant,
)

logger = logging.getLogger(__name__)


class TradeDraftManager:
    """Manages the lifecycle of TradeDraft objects."""

    def create_draft(self, user_id: str, raw_text: str) -> TradeDraft:
        """Create a new TradeDraft from a raw user message."""
        thesis = RawUserThesis(raw_text=raw_text, user_id=user_id)
        draft = TradeDraft(user_id=user_id, raw_thesis=thesis)
        logger.info("Created draft %s for user %s", draft.draft_id, user_id)
        return draft

    def update_draft(
        self,
        draft: TradeDraft,
        interpreted_thesis: InterpretedTradeThesis,
    ) -> TradeDraft:
        """Update the interpreted thesis on an existing draft."""
        draft.interpreted_thesis = interpreted_thesis
        draft.updated_at = datetime.now(timezone.utc)
        return draft

    def add_variant(self, draft: TradeDraft, variant: TradeVariant) -> TradeDraft:
        """Add a trade variant to the draft."""
        draft.variants.append(variant)
        draft.updated_at = datetime.now(timezone.utc)
        return draft

    def add_objection(self, draft: TradeDraft, objection: TradeObjection) -> TradeDraft:
        """Add an objection to the draft."""
        draft.objections.append(objection)
        draft.updated_at = datetime.now(timezone.utc)
        return draft

    def set_best_variant(self, draft: TradeDraft, variant: TradeVariant) -> TradeDraft:
        """Designate a variant as the current best."""
        draft.current_best_variant = variant
        draft.updated_at = datetime.now(timezone.utc)
        return draft

    def transition_status(self, draft: TradeDraft, new_status: TradeStatus) -> TradeDraft:
        """Transition the draft to a new status."""
        logger.info(
            "Draft %s: %s → %s", draft.draft_id, draft.status.value, new_status.value
        )
        draft.status = new_status
        draft.updated_at = datetime.now(timezone.utc)
        return draft

    def is_complete(self, draft: TradeDraft) -> tuple[bool, list[str]]:
        """Return (is_complete, list_of_missing_fields).

        A draft is *complete* when the interpreted thesis has all mandatory
        fields filled and a best variant has been selected.
        """
        missing: list[str] = []
        thesis = draft.interpreted_thesis
        if thesis is None:
            missing.append("interpreted_thesis")
        else:
            if not thesis.symbol:
                missing.append("symbol")
            if thesis.direction is None:
                missing.append("direction")
        if draft.current_best_variant is None:
            missing.append("current_best_variant")
        return (len(missing) == 0, missing)

    def to_decision(self, draft: TradeDraft) -> TradeDecision:
        """Convert a complete, confirmed draft to a TradeDecision.

        Raises ValueError if the draft is incomplete.
        """
        complete, missing = self.is_complete(draft)
        if not complete:
            raise ValueError(f"Draft incomplete — missing fields: {missing}")
        if draft.current_best_variant is None:
            raise ValueError("No best variant selected")

        thesis = draft.interpreted_thesis
        variant = draft.current_best_variant

        return TradeDecision(
            draft_id=draft.draft_id,
            symbol=thesis.symbol,  # type: ignore[arg-type]
            direction=thesis.direction,  # type: ignore[arg-type]
            entry_price=variant.entry_price,
            stop_loss=variant.stop_loss,
            take_profit=variant.take_profit,
            lot_size=variant.lot_size,
            risk_pct=variant.risk_pct,
            risk_reward_ratio=variant.risk_reward_ratio,
            rationale=variant.rationale,
        )
