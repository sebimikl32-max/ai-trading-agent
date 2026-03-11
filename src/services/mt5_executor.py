"""MT5 executor — initialize, connect, and submit orders."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.schemas.mt5 import MT5AccountInfo, MT5OrderRequest, MT5OrderResponse
from src.schemas.trade import ExecutionResult, TradeDecision, TradeDirection

logger = logging.getLogger(__name__)

# MT5 return code descriptions (subset)
_RETCODE_DESCRIPTIONS: dict[int, str] = {
    10004: "Requote",
    10006: "Request rejected",
    10007: "Request cancelled",
    10008: "Order placed",
    10009: "Request completed",
    10010: "Only part of the request was completed",
    10011: "Request processing error",
    10012: "Request cancelled by timeout",
    10013: "Invalid request",
    10014: "Invalid volume",
    10015: "Invalid price",
    10016: "Invalid stops",
    10017: "Trade disabled",
    10018: "Market is closed",
    10019: "Not enough money",
    10020: "Prices changed",
    10021: "No quotes",
    10022: "Invalid order expiration",
    10023: "Order state changed",
    10024: "Too frequent requests",
    10025: "No changes",
    10026: "Autotrading disabled by server",
    10027: "Autotrading disabled by client",
    10028: "Request locked for processing",
    10029: "Order or position frozen",
    10030: "Execution not supported",
    10031: "No connection",
    10032: "Only allowed for real accounts",
    10033: "Limit on number of pending orders",
    10034: "Limit on volume",
    10035: "Order type invalid",
    10036: "Position already closed",
    10038: "Close volume exceeds position volume",
    10039: "Close order already present",
    10040: "Maximum number of open positions is reached",
    10041: "Pending order activation denied",
    10042: "Rejected due to FIFO rule",
    10043: "Hedge prohibited",
}


class MT5Executor:
    """Async wrapper around MT5 order submission."""

    def __init__(
        self,
        path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ) -> None:
        self._path = path
        self._login = login
        self._password = password
        self._server = server
        self._initialized = False

    async def initialize(self) -> bool:
        """Connect to the MT5 terminal. Returns True on success."""
        result = await asyncio.to_thread(self._do_initialize)
        self._initialized = result
        return result

    async def shutdown(self) -> None:
        """Disconnect from MT5."""
        if self._initialized:
            await asyncio.to_thread(self._do_shutdown)
            self._initialized = False

    async def check_connection(self) -> bool:
        """Return True if the MT5 terminal is connected."""
        return await asyncio.to_thread(self._do_check_connection)

    async def execute_order(self, request: MT5OrderRequest) -> MT5OrderResponse:
        """Submit an order to MT5 and return the response."""
        if not self._initialized:
            raise RuntimeError("MT5Executor is not initialized. Call initialize() first.")
        return await asyncio.to_thread(self._do_execute, request)

    async def get_positions(self) -> list[dict]:
        """Return all open positions."""
        return await asyncio.to_thread(self._do_get_positions)

    # ── Thread-safe MT5 calls ──────────────────────────────────────────────────

    def _do_initialize(self) -> bool:
        try:
            import MetaTrader5 as mt5

            kwargs: dict = {}
            if self._path:
                kwargs["path"] = self._path
            if self._login:
                kwargs["login"] = self._login
            if self._password:
                kwargs["password"] = self._password
            if self._server:
                kwargs["server"] = self._server

            result = mt5.initialize(**kwargs)
            if not result:
                logger.error("MT5 initialization failed: %s", mt5.last_error())
            return bool(result)
        except ImportError:
            logger.error("MetaTrader5 package not available")
            return False
        except Exception as exc:
            logger.error("MT5 initialization error: %s", exc)
            return False

    def _do_shutdown(self) -> None:
        try:
            import MetaTrader5 as mt5

            mt5.shutdown()
        except Exception as exc:
            logger.warning("MT5 shutdown error: %s", exc)

    def _do_check_connection(self) -> bool:
        try:
            import MetaTrader5 as mt5

            info = mt5.terminal_info()
            return info is not None and info.connected
        except Exception:
            return False

    def _do_execute(self, request: MT5OrderRequest) -> MT5OrderResponse:
        try:
            import MetaTrader5 as mt5

            result = mt5.order_send(request.model_dump())
            if result is None:
                code, msg = mt5.last_error()
                return MT5OrderResponse(retcode=code, comment=msg)
            return MT5OrderResponse(
                retcode=result.retcode,
                deal=result.deal if result.deal else None,
                order=result.order if result.order else None,
                volume=result.volume if result.volume else None,
                price=result.price if result.price else None,
                comment=result.comment or "",
            )
        except Exception as exc:
            logger.error("_do_execute failed: %s", exc)
            return MT5OrderResponse(retcode=-1, comment=str(exc))

    def _do_get_positions(self) -> list[dict]:
        try:
            import MetaTrader5 as mt5

            positions = mt5.positions_get()
            if positions is None:
                return []
            return [p._asdict() for p in positions]
        except Exception as exc:
            logger.error("_do_get_positions failed: %s", exc)
            return []

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def build_execution_result(
        decision: TradeDecision,
        response: MT5OrderResponse,
    ) -> ExecutionResult:
        """Convert an MT5OrderResponse into an ExecutionResult."""
        success = response.retcode == 10009  # TRADE_RETCODE_DONE
        description = _RETCODE_DESCRIPTIONS.get(response.retcode, f"Unknown ({response.retcode})")
        slippage: Optional[float] = None
        if response.price and success:
            slippage = abs(decision.entry_price - response.price)

        return ExecutionResult(
            order_ticket=response.order,
            deal_id=response.deal,
            symbol=decision.symbol,
            direction=decision.direction,
            requested_price=decision.entry_price,
            fill_price=response.price,
            slippage=slippage,
            volume=decision.lot_size,
            retcode=response.retcode,
            retcode_description=description,
            success=success,
        )
