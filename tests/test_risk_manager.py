"""Tests for RiskManager."""

from __future__ import annotations

import pytest

from src.schemas.mt5 import MT5SymbolInfo
from src.services.risk_manager import RiskManager


class TestCalculateLotSize:
    def test_basic_eurusd(self, eurusd_symbol_info):
        rm = RiskManager()
        lots = rm.calculate_lot_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry=1.0920,
            stop_loss=1.0880,
            symbol_info=eurusd_symbol_info,
        )
        # risk_amount = 100 USD
        # stop_distance = 0.004 / 0.00001 = 400 points
        # lots = 100 / (400 * 0.1) = 2.5 → floored to step 0.01 → 2.50
        assert lots == pytest.approx(2.50, rel=1e-2)

    def test_lots_clamped_to_max(self, eurusd_symbol_info):
        rm = RiskManager()
        # Very small stop → huge lots → clamped to volume_max
        lots = rm.calculate_lot_size(
            account_balance=1_000_000.0,
            risk_pct=3.0,
            entry=1.0920,
            stop_loss=1.0919,  # 1 pip stop
            symbol_info=eurusd_symbol_info,
        )
        assert lots <= eurusd_symbol_info.volume_max

    def test_lots_clamped_to_min(self, eurusd_symbol_info):
        rm = RiskManager()
        # Tiny account, large stop → lots below min → clamped to volume_min
        lots = rm.calculate_lot_size(
            account_balance=100.0,
            risk_pct=0.1,
            entry=1.0920,
            stop_loss=1.0500,
            symbol_info=eurusd_symbol_info,
        )
        assert lots >= eurusd_symbol_info.volume_min

    def test_raises_on_zero_balance(self, eurusd_symbol_info):
        rm = RiskManager()
        with pytest.raises(ValueError, match="account_balance"):
            rm.calculate_lot_size(0.0, 1.0, 1.09, 1.08, eurusd_symbol_info)

    def test_raises_on_equal_entry_sl(self, eurusd_symbol_info):
        rm = RiskManager()
        with pytest.raises(ValueError, match="differ"):
            rm.calculate_lot_size(10_000.0, 1.0, 1.09, 1.09, eurusd_symbol_info)

    def test_xauusd_sizing(self, xauusd_symbol_info):
        rm = RiskManager()
        lots = rm.calculate_lot_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry=2320.0,
            stop_loss=2305.0,
            symbol_info=xauusd_symbol_info,
        )
        # Should be a valid lot size for XAUUSD
        assert xauusd_symbol_info.volume_min <= lots <= xauusd_symbol_info.volume_max


class TestValidateRisk:
    def test_valid_risk(self):
        rm = RiskManager(max_risk_pct=3.0)
        ok, msg = rm.validate_risk(1.0)
        assert ok is True
        assert msg == ""

    def test_exceeds_max(self):
        rm = RiskManager(max_risk_pct=3.0)
        ok, msg = rm.validate_risk(4.0)
        assert ok is False
        assert "4.00" in msg

    def test_zero_risk_invalid(self):
        rm = RiskManager()
        ok, msg = rm.validate_risk(0.0)
        assert ok is False


class TestCheckExposure:
    def test_within_limit(self):
        rm = RiskManager(max_positions=5)
        ok, msg = rm.check_exposure(3)
        assert ok is True

    def test_at_limit(self):
        rm = RiskManager(max_positions=5)
        ok, msg = rm.check_exposure(5)
        assert ok is False
        assert "5" in msg


class TestCalculateRiskReward:
    def test_long_rr(self):
        rm = RiskManager()
        rr = rm.calculate_risk_reward(entry=1.09, stop_loss=1.08, take_profit=1.11)
        assert rr == pytest.approx(2.0, rel=1e-2)

    def test_short_rr(self):
        rm = RiskManager()
        rr = rm.calculate_risk_reward(entry=1.09, stop_loss=1.10, take_profit=1.07)
        assert rr == pytest.approx(2.0, rel=1e-2)

    def test_zero_risk_returns_zero(self):
        rm = RiskManager()
        rr = rm.calculate_risk_reward(entry=1.09, stop_loss=1.09, take_profit=1.11)
        assert rr == 0.0
