"""Matrix delivery backend — sends alert messages as DMs via the Matrix HTTP API."""
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from portfolio_monitor.detectors.base import Alert

logger = logging.getLogger(__name__)


class MatrixDelivery:
    """Delivers alerts as plain-text DMs to a Matrix user.

    Required channel config params:
        homeserver   — e.g. "https://matrix.example.com"
        access_token — Matrix access token for the bot account

    The bot creates a DM room with each target user on first delivery and
    caches the room ID in memory for subsequent sends.
    """

    def __init__(self, homeserver: str, access_token: str, display_name: str = "Nexus Alert") -> None:
        self._homeserver: str = homeserver.rstrip("/")
        self._access_token: str = access_token
        self._display_name: str = display_name
        self._client: httpx.AsyncClient | None = None
        self._sender_id: str | None = None
        self._room_cache: dict[str, str] = {}  # target Matrix ID → room_id

    @classmethod
    def from_channel_params(cls, params: dict[str, Any]) -> "MatrixDelivery":
        return cls(
            homeserver=params["homeserver"],
            access_token=params["access_token"],
            display_name=params.get("display_name", "Nexus Alert"),
        )

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=15.0,
        )
        try:
            resp = await self._client.get(f"{self._homeserver}/_matrix/client/v3/account/whoami")
            if resp.status_code == 200:
                self._sender_id = resp.json().get("user_id")
                logger.info("MatrixDelivery connected as %s", self._sender_id)
            else:
                logger.warning("MatrixDelivery whoami failed (status=%d)", resp.status_code)
        except Exception:
            logger.exception("MatrixDelivery connect error")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._room_cache.clear()

    def _normalize_target(self, target: str) -> str:
        """Append homeserver domain if target is missing the server part."""
        if target.startswith("@") and ":" not in target:
            domain = urlparse(self._homeserver).hostname or ""
            return f"{target}:{domain}" if domain else target
        return target

    async def send_alert(self, alert: Alert, *, target: str = "") -> None:
        print("Senging alert", alert, target)
        if not target:
            logger.debug("MatrixDelivery: no target specified, skipping")
            return
        target = self._normalize_target(target)
        if self._client is None:
            logger.warning("MatrixDelivery.send_alert called before connect()")
            return
        try:
            room_id = await self._get_or_create_dm_room(target)
        except Exception:
            logger.exception("MatrixDelivery: failed to get/create DM room for %s", target)
            return

        body = f"[{self._display_name}] {alert.ticker.ticker}: {alert.message}"
        txn_id = f"{int(time.time() * 1000)}-{alert.id[:8]}"
        url = (
            f"{self._homeserver}/_matrix/client/v3/rooms/"
            f"{room_id}/send/m.room.message/{txn_id}"
        )
        try:
            resp = await self._client.put(url, json={"msgtype": "m.text", "body": body})
            if resp.status_code >= 400:
                logger.error(
                    "Matrix send failed (status=%d): %s", resp.status_code, resp.text[:200]
                )
        except Exception:
            logger.exception("MatrixDelivery send error for alert %s", alert.id)

    async def _get_or_create_dm_room(self, target: str) -> str:
        if target in self._room_cache:
            return self._room_cache[target]

        assert self._client is not None
        sender = self._sender_id or ""

        # Look for an existing DM room in account_data
        if sender:
            resp = await self._client.get(
                f"{self._homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct"
            )
            if resp.status_code == 200:
                dm_map: dict[str, list[str]] = resp.json()
                rooms = dm_map.get(target, [])
                if rooms:
                    self._room_cache[target] = rooms[0]
                    return rooms[0]

        # Create a new DM room
        resp = await self._client.post(
            f"{self._homeserver}/_matrix/client/v3/createRoom",
            json={
                "is_direct": True,
                "invite": [target],
                "preset": "trusted_private_chat",
            },
        )
        resp.raise_for_status()
        room_id: str = resp.json()["room_id"]

        # Persist in account_data so future bot restarts skip recreation
        if sender:
            existing_resp = await self._client.get(
                f"{self._homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct"
            )
            dm_map = existing_resp.json() if existing_resp.status_code == 200 else {}
            dm_map.setdefault(target, []).append(room_id)
            await self._client.put(
                f"{self._homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct",
                json=dm_map,
            )

        self._room_cache[target] = room_id
        logger.info("MatrixDelivery: created DM room %s for %s", room_id, target)
        return room_id
