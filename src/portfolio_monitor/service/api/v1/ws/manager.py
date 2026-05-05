import asyncio
import logging

import logfire
from pydantic import TypeAdapter, ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import DataProvider
from portfolio_monitor.portfolio.events import PriceUpdated
from portfolio_monitor.service.alerts.buffer import AlertBuffer, AlertBufferStore
from portfolio_monitor.service.settings import SessionStore
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.utils import logfire_set_attribute

from .messages import (
    AlertEventMessage,
    AlertReadMessage,
    AlertsClearedMessage,
    AllAlertsReadMessage,
    AssetSymbolParam,
    AuthenticateMessage,
    AuthenticatedMessage,
    ClientMessage,
    GetPreviousCloseMessage,
    GetPriceMessage,
    MarkAlertReadMessage,
    MarkAllAlertsReadMessage,
    PreviousCloseMessage,
    PriceMessage,
    PriceUpdateMessage,
    SubscribeAssetSymbolMessage,
    UnsubscribeAssetSymbolMessage,
    UnreadCountMessage,
    to_socket,
)

logger = logging.getLogger(__name__)

_AUTH_TIMEOUT = 10.0  # seconds to receive the authenticate message
_client_message = TypeAdapter(ClientMessage)


class WebSocketManager:
    """Routes PriceUpdated events and alert buffer events to subscribed WebSocket clients.

    Protocol (client → server):
      {"type": "authenticate",          "token": "<token>"}   ← must be first message
      {"type": "subscribe",             "symbols": [...]}
      {"type": "unsubscribe",           "symbols": [...]}
      {"type": "get_price",             "symbol": {...}}
      {"type": "get_previous_close",    "symbol": {...}}
      {"type": "mark_alert_read",       "alert_id": "..."}
      {"type": "mark_all_alerts_read"}

    Protocol (server → client):
      {"type": "authenticated"}
      {"type": "unread_count",    "unread_count": N}
      {"type": "price_update",    "symbol": {...}, "price": 182.50}
      {"type": "price",           "symbol": {...}, "price": 182.50, "timestamp": "..."}
      {"type": "previous_close",  "symbol": {...}, "price": 178.00, "timestamp": "..."}
      {"type": "alert_event",     "event": "fired"|"updated", "alert": {...}, "unread_count": N}
      {"type": "alert_read",      "alert_id": "...", "unread_count": N}
      {"type": "all_alerts_read", "unread_count": 0}
      {"type": "alerts_cleared",  "unread_count": 0}
    """

    def __init__(
        self,
        bus: EventBus,
        session_store: SessionStore,
        data_provider: DataProvider,
        alert_buffer_store: AlertBufferStore | None = None,
    ) -> None:
        self._session_store: SessionStore = session_store
        self._data_provider: DataProvider = data_provider
        self._alert_buffer_store: AlertBufferStore | None = alert_buffer_store
        self._connections: dict[WebSocket, set[AssetSymbol]] = {}
        bus.subscribe(PriceUpdated, self._on_price_updated)

    async def handle(self, ws: WebSocket) -> None:
        """Accept and serve a single WebSocket connection."""
        await ws.accept()
        try:
            first_text = await asyncio.wait_for(ws.receive_text(), timeout=_AUTH_TIMEOUT)
            msg = _client_message.validate_json(first_text)
        except WebSocketDisconnect:
            return
        except (asyncio.TimeoutError, ValidationError, ValueError, Exception):
            await ws.close(code=1008)
            return

        session = self._session_store.get(msg.token) if isinstance(msg, AuthenticateMessage) else None
        if session is None:
            print("Invalid auth token in WS connection attempt", ws.client)
            await ws.close(code=1008)
            return

        await ws.send_text(to_socket(AuthenticatedMessage()))
        self._connections[ws] = set()
        logger.debug("WS authenticated user=%s (total=%d)", session.username, len(self._connections))

        alert_task: asyncio.Task | None = None
        alert_buf: AlertBuffer | None = None
        alert_queue = None
        if self._alert_buffer_store is not None:
            alert_buf = self._alert_buffer_store.get_or_create(session.username)
            alert_queue = alert_buf.subscribe()
            alert_task = asyncio.create_task(self._push_alerts(ws, alert_queue))
            await ws.send_text(to_socket(UnreadCountMessage(unread_count=alert_buf.unread_count)))

        try:
            async for text in ws.iter_text():
                await self._handle_message(ws, text, alert_buf)
        except WebSocketDisconnect:
            pass
        finally:
            self._connections.pop(ws, None)
            if alert_task is not None:
                alert_task.cancel()
            if alert_buf is not None and alert_queue is not None:
                alert_buf.unsubscribe(alert_queue)
            logger.debug("WS disconnected (total=%d)", len(self._connections))

    async def _push_alerts(self, ws: WebSocket, queue: asyncio.Queue) -> None:
        try:
            while True:
                msg = await queue.get()
                event = msg.get("event")
                try:
                    if event in ("fired", "updated"):
                        await ws.send_text(to_socket(AlertEventMessage(
                            event=event,
                            alert=msg["alert"],
                            unread_count=msg["unread_count"],
                        )))
                    elif event == "read":
                        await ws.send_text(to_socket(AlertReadMessage(
                            alert_id=msg["alert_id"],
                            unread_count=msg["unread_count"],
                        )))
                    elif event == "all_read":
                        await ws.send_text(to_socket(AllAlertsReadMessage()))
                    elif event == "cleared":
                        await ws.send_text(to_socket(AlertsClearedMessage()))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    @logfire.instrument("ws.message")
    async def _handle_message(self, ws: WebSocket, text: str, alert_buf: AlertBuffer | None = None) -> None:
        try:
            msg = _client_message.validate_json(text)
        except (ValidationError, ValueError):
            return
        logfire_set_attribute("message_type", msg.type)
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
            case MarkAlertReadMessage():
                if alert_buf is not None:
                    alert_buf.mark_read(msg.alert_id)
            case MarkAllAlertsReadMessage():
                if alert_buf is not None:
                    alert_buf.mark_all_read()

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
