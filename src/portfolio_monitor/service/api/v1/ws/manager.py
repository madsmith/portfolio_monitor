import asyncio
import logging
from collections import defaultdict

import logfire
from pydantic import TypeAdapter, ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import Aggregate, DataProvider
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.portfolio.events import PriceUpdated
from portfolio_monitor.service.alerts.events import AlertStatusEvent, UserAlertDeletedEvent
from portfolio_monitor.session import SessionStore
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.utils import logfire_set_attribute

from .messages import (
    AlertDeletedMessage,
    AlertEventMessage,
    AlertReadMessage,
    AlertsClearedMessage,
    AllAlertsReadMessage,
    AssetSymbolParam,
    AuthenticateMessage,
    AuthenticatedMessage,
    ClientMessage,
    DeleteAlertMessage,
    GetPreviousCloseMessage,
    GetPriceMessage,
    GetWatchlistSnapshotMessage,
    MarkAlertReadMessage,
    MarkAllAlertsReadMessage,
    PreviousCloseMessage,
    PriceMessage,
    PriceUpdateMessage,
    SubscribeAssetSymbolMessage,
    UnsubscribeAssetSymbolMessage,
    UnreadCountMessage,
    WatchlistSnapshotEntry,
    WatchlistSnapshotMessage,
    to_socket,
)

logger = logging.getLogger(__name__)

_AUTH_TIMEOUT = 10.0
_client_message = TypeAdapter(ClientMessage)


class WebSocketManager:
    """Routes PriceUpdated and AlertStatusEvents to subscribed WebSocket clients.

    Protocol (client → server):
      {"type": "authenticate",          "token": "<token>"}   ← must be first message
      {"type": "subscribe",             "symbols": [...]}
      {"type": "unsubscribe",           "symbols": [...]}
      {"type": "get_price",             "symbol": {...}}
      {"type": "get_previous_close",    "symbol": {...}}
      {"type": "mark_alert_read",       "alert_id": "..."}
      {"type": "mark_all_alerts_read"}
      {"type": "delete_alert",          "alert_id": "..."}

    Protocol (server → client):
      {"type": "authenticated"}
      {"type": "unread_count",    "unread_count": N}
      {"type": "price_update",    "symbol": {...}, "price": 182.50}
      {"type": "price",           "symbol": {...}, "price": 182.50, "timestamp": "..."}
      {"type": "previous_close",  "symbol": {...}, "price": 178.00, "timestamp": "..."}
      {"type": "alert_event",     "event": "fired"|"updated", "alert": {...}, "unread_count": N}
      {"type": "alert_read",      "alert_id": "...", "unread_count": N}
      {"type": "alert_deleted",   "alert_id": "...", "unread_count": N}
      {"type": "all_alerts_read", "unread_count": 0}
      {"type": "alerts_cleared",  "unread_count": 0}
    """

    def __init__(
        self,
        bus: EventBus,
        session_store: SessionStore,
        data_provider: DataProvider,
        alerts_module: AlertsModule | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._session_store: SessionStore = session_store
        self._data_provider: DataProvider = data_provider
        self._alerts_module: AlertsModule | None = alerts_module
        self._connections: dict[WebSocket, set[AssetSymbol]] = {}
        self._user_sockets: dict[str, set[WebSocket]] = defaultdict(set)
        bus.subscribe(PriceUpdated, self._on_price_updated)
        if alerts_module is not None:
            bus.subscribe(AlertStatusEvent, self._on_alert_status_event)

    async def handle(self, ws: WebSocket) -> None:
        """Accept and serve a single WebSocket connection."""
        await ws.accept()
        try:
            first_text = await asyncio.wait_for(ws.receive_text(), timeout=_AUTH_TIMEOUT)
            msg = _client_message.validate_json(first_text)
        except WebSocketDisconnect:
            return
        except Exception:
            await ws.close(code=1008)
            return

        session = self._session_store.get(msg.token) if isinstance(msg, AuthenticateMessage) else None
        if session is None:
            logger.warning("Invalid auth token in WS connection attempt from %s", ws.client)
            await ws.close(code=1008)
            return

        await ws.send_text(to_socket(AuthenticatedMessage()))
        self._connections[ws] = set()
        self._user_sockets[session.username].add(ws)
        logger.debug("WS authenticated user=%s (total=%d)", session.username, len(self._connections))

        if self._alerts_module is not None:
            unread = self._alerts_module.get_unread_count(session.username)
            await ws.send_text(to_socket(UnreadCountMessage(unread_count=unread)))

        try:
            async for text in ws.iter_text():
                await self._handle_message(ws, text, session.username)
        except WebSocketDisconnect:
            pass
        finally:
            self._connections.pop(ws, None)
            self._user_sockets[session.username].discard(ws)
            logger.debug("WS disconnected user=%s (total=%d)", session.username, len(self._connections))

    @logfire.instrument("ws.message")
    async def _handle_message(self, ws: WebSocket, text: str, username: str) -> None:
        try:
            msg = _client_message.validate_json(text)
        except (ValidationError, ValueError):
            return
        logfire_set_attribute("message_type", msg.type)
        if self._alerts_module is None:
            return
        match msg:
            case SubscribeAssetSymbolMessage():
                self._connections[ws].update(s.to_asset_symbol() for s in msg.symbols)
            case UnsubscribeAssetSymbolMessage():
                self._connections[ws].difference_update(s.to_asset_symbol() for s in msg.symbols)
            case GetPriceMessage():
                aggregate = await self._data_provider.get_aggregate(msg.symbol.to_asset_symbol())
                if aggregate is not None:
                    await ws.send_text(to_socket(PriceMessage(
                        symbol=msg.symbol,
                        price=aggregate.close,
                        timestamp=aggregate.date_open,
                    )))
            case GetPreviousCloseMessage():
                aggregate = await self._data_provider.get_previous_close(msg.symbol.to_asset_symbol())
                if aggregate is not None:
                    await ws.send_text(to_socket(PreviousCloseMessage(
                        symbol=msg.symbol,
                        price=aggregate.close,
                        timestamp=aggregate.date_open,
                    )))
            case GetWatchlistSnapshotMessage():
                entries = await self._fetch_watchlist_snapshot(msg.symbols)
                await ws.send_text(to_socket(WatchlistSnapshotMessage(entries=entries)))
            case MarkAlertReadMessage():
                count = self._alerts_module.mark_record_read(username, msg.alert_id)
                await self._bus.publish(AlertStatusEvent(
                    username=username,
                    payload={"event": "read", "alert_id": msg.alert_id, "unread_count": count},
                ))
            case MarkAllAlertsReadMessage():
                self._alerts_module.mark_all_records_read(username)
                await self._bus.publish(AlertStatusEvent(
                    username=username,
                    payload={"event": "all_read", "unread_count": 0},
                ))
            case DeleteAlertMessage():
                count = self._alerts_module.delete_record(username, msg.alert_id)
                await self._bus.publish(AlertStatusEvent(
                    username=username,
                    payload={"event": "deleted", "alert_id": msg.alert_id, "unread_count": count},
                ))
                await self._bus.publish(UserAlertDeletedEvent(username=username, alert_id=msg.alert_id))

    async def _fetch_watchlist_snapshot(self, symbols: list[AssetSymbolParam]) -> list[WatchlistSnapshotEntry]:
        async def _one(param: AssetSymbolParam) -> WatchlistSnapshotEntry:
            symbol = param.to_asset_symbol()
            current, prev = await asyncio.gather(
                self._data_provider.get_aggregate(symbol),
                self._data_provider.get_previous_close(symbol),
                return_exceptions=True,
            )
            return WatchlistSnapshotEntry(
                symbol=param,
                price=current.close if isinstance(current, Aggregate) else None,
                prev_close=prev.close if isinstance(prev, Aggregate) else None,
            )

        results = await asyncio.gather(*[_one(s) for s in symbols], return_exceptions=True)
        return [r for r in results if isinstance(r, WatchlistSnapshotEntry)]

    async def _on_alert_status_event(self, event: AlertStatusEvent) -> None:
        sockets = self._user_sockets.get(event.username)
        if not sockets:
            return
        p = event.payload
        ev = p.get("event")
        if ev in ("fired", "updated"):
            text = to_socket(AlertEventMessage(event=ev, alert=p["alert"], unread_count=p["unread_count"]))
        elif ev == "read":
            text = to_socket(AlertReadMessage(alert_id=p["alert_id"], unread_count=p["unread_count"]))
        elif ev == "deleted":
            text = to_socket(AlertDeletedMessage(alert_id=p["alert_id"], unread_count=p["unread_count"]))
        elif ev == "all_read":
            text = to_socket(AllAlertsReadMessage())
        elif ev == "cleared":
            text = to_socket(AlertsClearedMessage())
        else:
            return
        dead: list[WebSocket] = []
        for ws in list(sockets):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    async def _on_price_updated(self, event: PriceUpdated) -> None:
        payload = to_socket(PriceUpdateMessage(
            symbol=AssetSymbolParam.from_asset_symbol(event.symbol),
            price=float(event.price._value),
        ))
        dead: list[WebSocket] = []
        for ws, symbols in list(self._connections.items()):
            if event.symbol not in symbols:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.pop(ws, None)
