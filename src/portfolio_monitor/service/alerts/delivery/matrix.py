"""Matrix delivery backend — sends alert messages to a Matrix room via HTTP API."""
import logging
import time
from typing import Any

import httpx

from portfolio_monitor.detectors.base import Alert

logger = logging.getLogger(__name__)


class MatrixDelivery:
    """Delivers alerts as plain-text messages to a Matrix room.

    Required channel params:
        homeserver   — e.g. "https://matrix.example.com"
        access_token — Matrix access token with send permissions
        room_id      — e.g. "!abc123:example.com"

    Optional:
        display_name — prefix shown in the message (default "Nexus Alert")
    """

    def __init__(
        self,
        homeserver: str,
        access_token: str,
        room_id: str,
        display_name: str = "Nexus Alert",
    ) -> None:
        self._homeserver: str = homeserver.rstrip("/")
        self._access_token: str = access_token
        self._room_id: str = room_id
        self._display_name: str = display_name
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_channel_params(cls, params: dict[str, Any]) -> "MatrixDelivery":
        return cls(
            homeserver=params["homeserver"],
            access_token=params["access_token"],
            room_id=params["room_id"],
            display_name=params.get("display_name", "Nexus Alert"),
        )

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=10.0,
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_alert(self, alert: Alert) -> None:
        if self._client is None:
            logger.warning("MatrixDelivery.send_alert called before connect()")
            return
        body = f"[{self._display_name}] {alert.ticker.ticker}: {alert.message}"
        txn_id = f"{int(time.time() * 1000)}-{alert.id[:8]}"
        url = (
            f"{self._homeserver}/_matrix/client/v3/rooms/"
            f"{self._room_id}/send/m.room.message/{txn_id}"
        )
        try:
            resp = await self._client.put(
                url,
                json={"msgtype": "m.text", "body": body},
            )
            if resp.status_code >= 400:
                logger.error(
                    "Matrix delivery failed (status=%d): %s", resp.status_code, resp.text[:200]
                )
        except Exception:
            logger.exception("Matrix delivery error for alert %s", alert.id)
