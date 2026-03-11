"""MetaTrader 5 request/response Pydantic v2 schemas."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class MT5OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class MT5OrderRequest(BaseModel):
    """Mirror of the dict passed to mt5.order_send()."""

    action: int
    symbol: str
    volume: float
    type: int
    price: float
    sl: float
    tp: float
    deviation: int = 20
    magic: int = 234000
    comment: str = "ai-trading-agent"
    type_time: int = 0   # ORDER_TIME_GTC
    type_filling: int = 2  # ORDER_FILLING_IOC


class MT5OrderResponse(BaseModel):
    """Parsed response from mt5.order_send()."""

    retcode: int
    deal: Optional[int] = None
    order: Optional[int] = None
    volume: Optional[float] = None
    price: Optional[float] = None
    comment: str = ""


class MT5AccountInfo(BaseModel):
    """Subset of mt5.account_info() fields."""

    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    server: str


class MT5SymbolInfo(BaseModel):
    """Subset of mt5.symbol_info() fields used for position sizing."""

    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: Optional[float] = None
    volume_min: float
    volume_max: float
    volume_step: float
    trade_contract_size: float
