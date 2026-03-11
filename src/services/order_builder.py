"""Order builder — construct MT5 order requests from TradeDecision objects."""

from __future__ import annotations

import logging

from src.schemas.mt5 import MT5OrderRequest, MT5OrderType
from src.schemas.trade import TradeDecision, TradeDirection

logger = logging.getLogger(__name__)

# MT5 constants
_TRADE_ACTION_DEAL = 1       # ORDER_TYPE_BUY / SELL (market execution)
_ORDER_TIME_GTC = 0
_ORDER_FILLING_IOC = 2

# MT5 order type codes
_MT5_ORDER_TYPE: dict[TradeDirection, int] = {
    TradeDirection.LONG: 0,   # ORDER_TYPE_BUY
    TradeDirection.SHORT: 1,  # ORDER_TYPE_SELL
}


class OrderBuilder:
    """Builds MT5OrderRequest objects from confirmed TradeDecision instances."""

    def __init__(self, magic_number: int = 234000, deviation: int = 20) -> None:
        self.magic_number = magic_number
        self.deviation = deviation

    def build_market_order(self, decision: TradeDecision) -> MT5OrderRequest:
        """Build a market order request from a TradeDecision."""
        order_type = _MT5_ORDER_TYPE[decision.direction]
        request = MT5OrderRequest(
            action=_TRADE_ACTION_DEAL,
            symbol=decision.symbol,
            volume=decision.lot_size,
            type=order_type,
            price=decision.entry_price,
            sl=decision.stop_loss,
            tp=decision.take_profit,
            deviation=self.deviation,
            magic=self.magic_number,
            comment=f"ai-agent:{decision.decision_id[:8]}",
            type_time=_ORDER_TIME_GTC,
            type_filling=_ORDER_FILLING_IOC,
        )
        logger.info(
            "Built market order for %s %s lot=%.2f",
            decision.direction.value,
            decision.symbol,
            decision.lot_size,
        )
        return request

    def validate_order(self, request: MT5OrderRequest) -> tuple[bool, list[str]]:
        """Validate an MT5OrderRequest before submission.

        Returns (is_valid, list_of_errors).
        """
        errors: list[str] = []

        if not request.symbol:
            errors.append("Symbol is required")
        if request.volume <= 0:
            errors.append(f"Volume must be positive (got {request.volume})")
        if request.price <= 0:
            errors.append(f"Price must be positive (got {request.price})")
        if request.sl <= 0:
            errors.append(f"Stop loss must be positive (got {request.sl})")
        if request.tp <= 0:
            errors.append(f"Take profit must be positive (got {request.tp})")

        # Directional consistency
        if request.type == _MT5_ORDER_TYPE[TradeDirection.LONG]:
            if request.sl >= request.price:
                errors.append(
                    f"BUY: stop loss ({request.sl}) must be below entry price ({request.price})"
                )
            if request.tp <= request.price:
                errors.append(
                    f"BUY: take profit ({request.tp}) must be above entry price ({request.price})"
                )
        elif request.type == _MT5_ORDER_TYPE[TradeDirection.SHORT]:
            if request.sl <= request.price:
                errors.append(
                    f"SELL: stop loss ({request.sl}) must be above entry price ({request.price})"
                )
            if request.tp >= request.price:
                errors.append(
                    f"SELL: take profit ({request.tp}) must be below entry price ({request.price})"
                )

        return (len(errors) == 0, errors)

    def to_mt5_dict(self, request: MT5OrderRequest) -> dict:
        """Convert to the dict format expected by mt5.order_send()."""
        return request.model_dump()
