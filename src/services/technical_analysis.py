"""Technical analysis service — compute indicators from OHLCV bars."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from src.schemas.market import MarketSnapshot, OHLCVBar, TechnicalFeatures

logger = logging.getLogger(__name__)


class TechnicalAnalysisService:
    """Compute technical features from a MarketSnapshot."""

    def compute_features(self, snapshot: MarketSnapshot) -> TechnicalFeatures:
        bars = snapshot.recent_bars
        if not bars:
            logger.warning("No bars provided for technical analysis")
            return TechnicalFeatures()

        closes = np.array([b.close for b in bars], dtype=float)
        highs = np.array([b.high for b in bars], dtype=float)
        lows = np.array([b.low for b in bars], dtype=float)
        volumes = np.array([b.volume for b in bars], dtype=float)

        features = TechnicalFeatures(
            atr_14=self._atr(highs, lows, closes, 14),
            rsi_14=self._rsi(closes, 14),
            sma_20=self._sma(closes, 20),
            sma_50=self._sma(closes, 50),
            sma_200=self._sma(closes, 200),
            recent_swing_high=self._swing_high(highs, 5),
            recent_swing_low=self._swing_low(lows, 5),
            daily_range=self._daily_range(highs, lows),
            current_spread=snapshot.tick.spread,
            volatility_percentile=self._volatility_percentile(highs, lows, closes),
        )
        return features

    # ── Indicators ─────────────────────────────────────────────────────────────

    @staticmethod
    def _sma(arr: np.ndarray, period: int) -> Optional[float]:
        if len(arr) < period:
            return None
        return float(np.mean(arr[-period:]))

    @staticmethod
    def _atr(
        highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
    ) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        prev_closes = closes[:-1]
        curr_highs = highs[1:]
        curr_lows = lows[1:]
        tr = np.maximum(
            curr_highs - curr_lows,
            np.maximum(
                np.abs(curr_highs - prev_closes),
                np.abs(curr_lows - prev_closes),
            ),
        )
        if len(tr) < period:
            return None
        return float(np.mean(tr[-period:]))

    @staticmethod
    def _rsi(closes: np.ndarray, period: int) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        deltas = np.diff(closes[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @staticmethod
    def _swing_high(highs: np.ndarray, lookback: int) -> Optional[float]:
        if len(highs) < lookback:
            return None
        return float(np.max(highs[-lookback:]))

    @staticmethod
    def _swing_low(lows: np.ndarray, lookback: int) -> Optional[float]:
        if len(lows) < lookback:
            return None
        return float(np.min(lows[-lookback:]))

    @staticmethod
    def _daily_range(highs: np.ndarray, lows: np.ndarray) -> Optional[float]:
        if len(highs) == 0:
            return None
        return float(highs[-1] - lows[-1])

    @staticmethod
    def _volatility_percentile(
        highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 20
    ) -> Optional[float]:
        """Return current ATR as a percentile of the last *period* ATR values."""
        if len(closes) < period + 2:
            return None
        prev_closes = closes[:-1]
        curr_highs = highs[1:]
        curr_lows = lows[1:]
        tr = np.maximum(
            curr_highs - curr_lows,
            np.maximum(
                np.abs(curr_highs - prev_closes),
                np.abs(curr_lows - prev_closes),
            ),
        )
        if len(tr) < period:
            return None
        window = tr[-period:]
        current_tr = float(tr[-1])
        percentile = float(np.sum(window <= current_tr) / len(window) * 100)
        return percentile
