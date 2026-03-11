"""Market data service — wraps MetaTrader 5 API calls with async and caching."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from src.schemas.market import MarketContext, MarketSnapshot, OHLCVBar, TickData
from src.schemas.mt5 import MT5AccountInfo, MT5SymbolInfo

logger = logging.getLogger(__name__)

# MT5 timeframe constants (values match mt5 module)
_TIMEFRAMES: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 16385,
    "H4": 16388,
    "D1": 16408,
    "W1": 32769,
    "MN1": 49153,
}


class MarketDataService:
    """Async wrapper around MetaTrader 5 market data functions.

    All MT5 calls run in a thread pool (asyncio.to_thread) because the
    MetaTrader5 Python package is synchronous.
    """

    def __init__(self, ttl_seconds: int = 5) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, object]] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    async def get_tick(self, symbol: str) -> Optional[TickData]:
        """Return the latest tick for *symbol*."""
        return await asyncio.to_thread(self._fetch_tick, symbol)

    async def get_bars(
        self, symbol: str, timeframe: str, count: int = 200
    ) -> list[OHLCVBar]:
        """Return the last *count* OHLCV bars for *symbol*."""
        cache_key = f"bars:{symbol}:{timeframe}:{count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        bars = await asyncio.to_thread(self._fetch_bars, symbol, timeframe, count)
        self._set_cache(cache_key, bars)
        return bars

    async def get_snapshot(
        self, symbol: str, timeframe: str = "H1", bars: int = 200
    ) -> Optional[MarketSnapshot]:
        """Return a MarketSnapshot combining tick + bars."""
        tick = await self.get_tick(symbol)
        if tick is None:
            return None
        bar_list = await self.get_bars(symbol, timeframe, bars)
        return MarketSnapshot(symbol=symbol, tick=tick, recent_bars=bar_list, timeframe=timeframe)

    async def get_symbol_info(self, symbol: str) -> Optional[MT5SymbolInfo]:
        """Return symbol metadata for position sizing."""
        return await asyncio.to_thread(self._fetch_symbol_info, symbol)

    async def get_account_info(self) -> Optional[MT5AccountInfo]:
        """Return the current account details."""
        return await asyncio.to_thread(self._fetch_account_info)

    # ── Thread-safe MT5 calls ──────────────────────────────────────────────────

    @staticmethod
    def _fetch_tick(symbol: str) -> Optional[TickData]:
        try:
            import MetaTrader5 as mt5

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.warning("No tick data for %s", symbol)
                return None
            spread = round((tick.ask - tick.bid) / _get_point(symbol), 1)
            return TickData(
                bid=tick.bid,
                ask=tick.ask,
                spread=tick.ask - tick.bid,
                last=tick.last if tick.last else None,
                volume=tick.volume if tick.volume else None,
                timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
            )
        except Exception as exc:
            logger.error("_fetch_tick failed for %s: %s", symbol, exc)
            return None

    @staticmethod
    def _fetch_bars(symbol: str, timeframe: str, count: int) -> list[OHLCVBar]:
        try:
            import MetaTrader5 as mt5

            tf = _TIMEFRAMES.get(timeframe.upper(), 16385)  # default H1
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is None:
                logger.warning("No bar data for %s %s", symbol, timeframe)
                return []
            return [
                OHLCVBar(
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["tick_volume"]),
                    timestamp=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                )
                for r in rates
            ]
        except Exception as exc:
            logger.error("_fetch_bars failed for %s %s: %s", symbol, timeframe, exc)
            return []

    @staticmethod
    def _fetch_symbol_info(symbol: str) -> Optional[MT5SymbolInfo]:
        try:
            import MetaTrader5 as mt5

            info = mt5.symbol_info(symbol)
            if info is None:
                logger.warning("No symbol info for %s", symbol)
                return None
            return MT5SymbolInfo(
                name=info.name,
                digits=info.digits,
                point=info.point,
                trade_tick_size=info.trade_tick_size,
                trade_tick_value=info.trade_tick_value if info.trade_tick_value else None,
                volume_min=info.volume_min,
                volume_max=info.volume_max,
                volume_step=info.volume_step,
                trade_contract_size=info.trade_contract_size,
            )
        except Exception as exc:
            logger.error("_fetch_symbol_info failed for %s: %s", symbol, exc)
            return None

    @staticmethod
    def _fetch_account_info() -> Optional[MT5AccountInfo]:
        try:
            import MetaTrader5 as mt5

            info = mt5.account_info()
            if info is None:
                return None
            return MT5AccountInfo(
                login=info.login,
                balance=info.balance,
                equity=info.equity,
                margin=info.margin,
                free_margin=info.margin_free,
                leverage=info.leverage,
                currency=info.currency,
                server=info.server,
            )
        except Exception as exc:
            logger.error("_fetch_account_info failed: %s", exc)
            return None

    # ── TTL cache ──────────────────────────────────────────────────────────────

    def _get_cached(self, key: str) -> Optional[object]:
        if key in self._cache:
            ts, value = self._cache[key]
            if (datetime.now(timezone.utc).timestamp() - ts) < self._ttl:
                return value
        return None

    def _set_cache(self, key: str, value: object) -> None:
        self._cache[key] = (datetime.now(timezone.utc).timestamp(), value)


def _get_point(symbol: str) -> float:
    """Return the point size for *symbol*, defaulting to 0.00001 (5-digit forex)."""
    try:
        import MetaTrader5 as mt5

        info = mt5.symbol_info(symbol)
        if info:
            return info.point
    except Exception:
        pass
    return 0.00001
