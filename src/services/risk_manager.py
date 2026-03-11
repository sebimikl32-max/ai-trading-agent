"""Risk manager — position sizing and risk validation."""

from __future__ import annotations

import logging
import math

from src.schemas.mt5 import MT5SymbolInfo

logger = logging.getLogger(__name__)


class RiskManager:
    """Calculates lot sizes and validates risk parameters."""

    def __init__(self, max_risk_pct: float = 3.0, max_positions: int = 5) -> None:
        self.max_risk_pct = max_risk_pct
        self.max_positions = max_positions

    # ── Position sizing ────────────────────────────────────────────────────────

    def calculate_lot_size(
        self,
        account_balance: float,
        risk_pct: float,
        entry: float,
        stop_loss: float,
        symbol_info: MT5SymbolInfo,
    ) -> float:
        """Return lot size rounded to the symbol's volume step.

        Formula:
            risk_amount = balance × (risk_pct / 100)
            stop_distance_points = |entry - stop_loss| / point
            tick_value = trade_tick_value or (point / trade_tick_size)
            lots = risk_amount / (stop_distance_points × tick_value × contract_size)
        """
        if account_balance <= 0:
            raise ValueError("account_balance must be positive")
        if risk_pct <= 0:
            raise ValueError("risk_pct must be positive")
        if entry == stop_loss:
            raise ValueError("entry and stop_loss must differ")

        risk_amount = account_balance * (risk_pct / 100.0)
        stop_distance = abs(entry - stop_loss)
        stop_distance_in_points = stop_distance / symbol_info.point

        tick_value = (
            symbol_info.trade_tick_value
            if symbol_info.trade_tick_value
            else symbol_info.point / symbol_info.trade_tick_size
        )

        raw_lots = risk_amount / (stop_distance_in_points * tick_value)

        # Round down to the nearest volume step
        step = symbol_info.volume_step
        lots = math.floor(raw_lots / step) * step
        lots = round(lots, _decimal_places(step))

        # Clamp to symbol limits
        lots = max(symbol_info.volume_min, min(symbol_info.volume_max, lots))
        return lots

    # ── Validation ─────────────────────────────────────────────────────────────

    def validate_risk(self, risk_pct: float) -> tuple[bool, str]:
        """Return (is_valid, reason)."""
        if risk_pct <= 0:
            return False, "risk_pct must be positive"
        if risk_pct > self.max_risk_pct:
            return False, f"risk_pct {risk_pct:.2f}% exceeds maximum {self.max_risk_pct:.2f}%"
        return True, ""

    def check_exposure(self, open_positions: int) -> tuple[bool, str]:
        """Return (within_limit, reason)."""
        if open_positions >= self.max_positions:
            return False, (
                f"Already at maximum positions ({self.max_positions}). "
                "Close or reduce before adding a new trade."
            )
        return True, ""

    def calculate_risk_reward(
        self, entry: float, stop_loss: float, take_profit: float
    ) -> float:
        """Return risk:reward ratio (reward / risk). Returns 0 if risk is 0."""
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0.0
        return round(reward / risk, 2)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _decimal_places(step: float) -> int:
    """Return number of decimal places in *step* for clean rounding."""
    s = f"{step:.10f}".rstrip("0")
    if "." in s:
        return len(s.split(".")[1])
    return 0
