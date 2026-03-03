from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from portfolio_monitor.service.types import AssetSymbol, AssetTypes

# ---------------------------------------------------------------------------
# Shared sub-model
# ---------------------------------------------------------------------------


class AssetSymbolParam(BaseModel):
    ticker: str
    type: AssetTypes  # validated against the AssetTypes enum

    def to_asset_symbol(self) -> AssetSymbol:
        return AssetSymbol(ticker=self.ticker, asset_type=self.type)

    @classmethod
    def from_asset_symbol(cls, symbol: AssetSymbol) -> "AssetSymbolParam":
        return cls(ticker=symbol.ticker, type=symbol.asset_type)

# ---------------------------------------------------------------------------
# Client → server
# ---------------------------------------------------------------------------


class AuthenticateMessage(BaseModel):
    type: Literal["authenticate"]
    token: str


class SubscribeAssetSymbolMessage(BaseModel):
    type: Literal["subscribe"]
    symbols: list[AssetSymbolParam]


class UnsubscribeAssetSymbolMessage(BaseModel):
    type: Literal["unsubscribe"]
    symbols: list[AssetSymbolParam]


class GetPriceMessage(BaseModel):
    type: Literal["get_price"]
    symbol: AssetSymbolParam


class GetPreviousCloseMessage(BaseModel):
    type: Literal["get_previous_close"]
    symbol: AssetSymbolParam


ClientMessage = Annotated[
    Union[
        AuthenticateMessage,
        SubscribeAssetSymbolMessage,
        UnsubscribeAssetSymbolMessage,
        GetPriceMessage,
        GetPreviousCloseMessage,
    ],
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# Server → client
# ---------------------------------------------------------------------------


class AuthenticatedMessage(BaseModel):
    type: Literal["authenticated"] = "authenticated"


class PriceUpdateMessage(BaseModel):
    type: Literal["price_update"] = "price_update"
    symbol: AssetSymbolParam
    price: float


class PriceMessage(BaseModel):
    type: Literal["price"] = "price"
    symbol: AssetSymbolParam
    price: float
    timestamp: datetime


class PreviousCloseMessage(BaseModel):
    type: Literal["previous_close"] = "previous_close"
    symbol: AssetSymbolParam
    price: float
    timestamp: datetime


ServerMessage = AuthenticatedMessage | PriceUpdateMessage | PriceMessage | PreviousCloseMessage


def to_socket(msg: ServerMessage) -> str:
    """Serialize a server-to-client message to a JSON string."""
    return msg.model_dump_json()
