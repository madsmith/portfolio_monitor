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


class MarkAlertReadMessage(BaseModel):
    type: Literal["mark_alert_read"]
    alert_id: str


class MarkAllAlertsReadMessage(BaseModel):
    type: Literal["mark_all_alerts_read"]


class DeleteAlertMessage(BaseModel):
    type: Literal["delete_alert"]
    alert_id: str


class GetWatchlistSnapshotMessage(BaseModel):
    type: Literal["get_watchlist_snapshot"]
    symbols: list[AssetSymbolParam]


ClientMessage = Annotated[
    Union[
        AuthenticateMessage,
        SubscribeAssetSymbolMessage,
        UnsubscribeAssetSymbolMessage,
        GetPriceMessage,
        GetPreviousCloseMessage,
        GetWatchlistSnapshotMessage,
        MarkAlertReadMessage,
        MarkAllAlertsReadMessage,
        DeleteAlertMessage,
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


class AlertEventMessage(BaseModel):
    """Fired when an alert is first raised or updated while still active."""
    type: Literal["alert_event"] = "alert_event"
    event: Literal["fired", "updated"]
    alert: dict  # includes "read" field
    unread_count: int


class AlertReadMessage(BaseModel):
    """Fired when a single alert is marked read."""
    type: Literal["alert_read"] = "alert_read"
    alert_id: str
    unread_count: int


class AllAlertsReadMessage(BaseModel):
    """Fired when all alerts are marked read."""
    type: Literal["all_alerts_read"] = "all_alerts_read"
    unread_count: int = 0


class AlertDeletedMessage(BaseModel):
    """Fired when a single alert is deleted from the buffer."""
    type: Literal["alert_deleted"] = "alert_deleted"
    alert_id: str
    unread_count: int


class AlertsClearedMessage(BaseModel):
    """Fired when all alerts are deleted from the buffer."""
    type: Literal["alerts_cleared"] = "alerts_cleared"
    unread_count: int = 0


class UnreadCountMessage(BaseModel):
    """Sent once after authentication to sync the current unread count."""
    type: Literal["unread_count"] = "unread_count"
    unread_count: int


class WatchlistSnapshotEntry(BaseModel):
    symbol: AssetSymbolParam
    price: float | None
    prev_close: float | None


class WatchlistSnapshotMessage(BaseModel):
    """Response to get_watchlist_snapshot — current price + prev close for each requested symbol."""
    type: Literal["watchlist_snapshot"] = "watchlist_snapshot"
    entries: list[WatchlistSnapshotEntry]


ServerMessage = (
    AuthenticatedMessage
    | PriceUpdateMessage
    | PriceMessage
    | PreviousCloseMessage
    | AlertEventMessage
    | AlertReadMessage
    | AllAlertsReadMessage
    | AlertDeletedMessage
    | AlertsClearedMessage
    | UnreadCountMessage
    | WatchlistSnapshotMessage
)


def to_socket(msg: ServerMessage) -> str:
    """Serialize a server-to-client message to a JSON string."""
    return msg.model_dump_json()
