import asyncio
import hmac
import logging

from pydantic import TypeAdapter, ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.portfolio.events import PriceUpdated
from portfolio_monitor.service.types import AssetSymbol

from .messages import (
    AssetSymbolParam,
    AuthenticateMessage,
    AuthenticatedMessage,
    ClientMessage,
    PriceUpdateMessage,
    SubscribeAssetSymbolMessage,
    UnsubscribeAssetSymbolMessage,
    to_socket,
)

logger = logging.getLogger(__name__)

_AUTH_TIMEOUT = 10.0  # seconds to receive the authenticate message
_client_message = TypeAdapter(ClientMessage)


class WebSocketManager:
    """Routes PriceUpdated events to subscribed WebSocket clients.

    Protocol (client → server):
      {"type": "authenticate", "token": "<auth_key>"}   ← must be first message
      {"type": "subscribe",    "symbols": [{"ticker": "AAPL", "type": "stock"}]}
      {"type": "unsubscribe",  "symbols": [{"ticker": "AAPL", "type": "stock"}]}

    Protocol (server → client):
      {"type": "authenticated"}
      {"type": "price_update", "symbol": {"ticker": "AAPL", "type": "stock"}, "price": 182.50}
    """

    def __init__(self, bus: EventBus, auth_key: str) -> None:
        self._auth_key: str = auth_key
        # Maps each authenticated WebSocket to the set of AssetSymbols it has subscribed to
        self._connections: dict[WebSocket, set[AssetSymbol]] = {}
        bus.subscribe(PriceUpdated, self._on_price_updated)

    async def handle(self, ws: WebSocket) -> None:
        """Accept and serve a single WebSocket connection."""
        await ws.accept()
        try:
            first_text = await asyncio.wait_for(ws.receive_text(), timeout=_AUTH_TIMEOUT)
            msg = _client_message.validate_json(first_text)
        except (asyncio.TimeoutError, ValidationError, ValueError, Exception):
            await ws.close(code=1008)
            return

        if not isinstance(msg, AuthenticateMessage) or not hmac.compare_digest(
            msg.token, self._auth_key
        ):
            await ws.close(code=1008)
            return

        await ws.send_text(to_socket(AuthenticatedMessage()))
        self._connections[ws] = set()
        logger.debug("WS authenticated (total=%d)", len(self._connections))
        try:
            async for text in ws.iter_text():
                self._handle_message(ws, text)
        except WebSocketDisconnect:
            pass
        finally:
            self._connections.pop(ws, None)
            logger.debug("WS disconnected (total=%d)", len(self._connections))

    def _handle_message(self, ws: WebSocket, text: str) -> None:
        try:
            msg = _client_message.validate_json(text)
        except (ValidationError, ValueError):
            return
        match msg:
            case SubscribeAssetSymbolMessage():
                self._connections[ws].update(s.to_asset_symbol() for s in msg.symbols)
            case UnsubscribeAssetSymbolMessage():
                self._connections[ws].difference_update(s.to_asset_symbol() for s in msg.symbols)

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
