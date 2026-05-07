"""Matrix delivery backend — sends alert messages as DMs via the Matrix HTTP API."""
import logging
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import httpx

from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.service.alerts.delivery.base import AlertEventType

logger = logging.getLogger(__name__)


class MatrixDelivery:
    """Delivers alerts as plain-text DMs to a Matrix user.

    Required channel config params:
        homeserver   — e.g. "https://matrix.example.com"
        access_token — Matrix access token for the bot account

    The bot creates a DM room with each target user on first delivery and
    caches the room ID in memory for subsequent sends.
    """

    _MAX_TRACKED_EVENTS = 30
    _REDACTED = "_redacted"  # sentinel: alert was sent, redacted, and should not re-fire

    def __init__(self, homeserver: str, access_token: str, display_name: str = "Nexus Alert") -> None:
        self._homeserver: str = homeserver.rstrip("/")
        self._access_token: str = access_token
        self._display_name: str = display_name
        self._client: httpx.AsyncClient | None = None
        self._sender_id: str | None = None
        self._room_cache: dict[str, str] = {}  # target → room_id
        self._sent_events: dict[str, OrderedDict[str, str]] = {}  # target → (alert_id → event_id)

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
        self._sent_events.clear()

    def _store_event(self, target: str, alert_id: str, event_id: str) -> None:
        cache = self._sent_events.setdefault(target, OrderedDict())
        cache[alert_id] = event_id
        if len(cache) > self._MAX_TRACKED_EVENTS:
            cache.popitem(last=False)

    def _get_event(self, target: str, alert_id: str) -> str | None:
        return self._sent_events.get(target, {}).get(alert_id)

    def _normalize_target(self, target: str) -> str:
        """Append homeserver domain if target is missing the server part."""
        if target.startswith("@") and ":" not in target:
            domain = urlparse(self._homeserver).hostname or ""
            return f"{target}:{domain}" if domain else target
        return target

    async def send_alert(self, alert: Alert, *, target: str = "", event: AlertEventType = AlertEventType.FIRED) -> None:
        if not target:
            logger.debug("MatrixDelivery: no target specified, skipping")
            return
        target = self._normalize_target(target)
        if self._client is None:
            logger.warning("MatrixDelivery.send_alert called before connect()")
            return

        if event == AlertEventType.CLEARED:
            await self._redact_alert(alert, target)
            return

        cached = self._get_event(target, alert.id)
        if cached == self._REDACTED:
            logger.debug("MatrixDelivery: suppressing re-fire of redacted alert %s", alert.id[:8])
            return

        try:
            room_id = await self._get_or_create_dm_room(target)
        except Exception:
            logger.exception("MatrixDelivery: failed to get/create DM room for %s", target)
            return

        body = f"[{self._display_name}] {alert.ticker.ticker}: {alert.message}"
        txn_id = f"{int(time.time() * 1000)}-{alert.id[:8]}"

        existing_event_id = cached if event == AlertEventType.UPDATED else None

        if existing_event_id:
            payload: dict[str, Any] = {
                "msgtype": "m.text",
                "body": f"* {body}",
                "m.new_content": {"msgtype": "m.text", "body": body},
                "m.relates_to": {"rel_type": "m.replace", "event_id": existing_event_id},
            }
        else:
            payload = {"msgtype": "m.text", "body": body}

        url = f"{self._homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
        try:
            resp = await self._client.put(url, json=payload)
            if resp.status_code >= 400:
                logger.error("Matrix send failed (status=%d): %s", resp.status_code, resp.text[:200])
            elif not existing_event_id:
                event_id = resp.json().get("event_id", "")
                if event_id:
                    self._store_event(target, alert.id, event_id)
        except Exception:
            logger.exception("MatrixDelivery send error for alert %s", alert.id)

    async def _redact_alert(self, alert: Alert, target: str) -> None:
        event_id = self._get_event(target, alert.id)
        if not event_id or event_id == self._REDACTED:
            return
        try:
            room_id = await self._get_or_create_dm_room(target)
        except Exception:
            logger.exception("MatrixDelivery: failed to get room for redaction, target=%s", target)
            return
        txn_id = f"redact-{int(time.time() * 1000)}-{alert.id[:8]}"
        url = f"{self._homeserver}/_matrix/client/v3/rooms/{room_id}/redact/{event_id}/{txn_id}"
        try:
            resp = await self._client.put(url, json={"reason": "alert cleared"})  # type: ignore[union-attr]
            if resp.status_code >= 400:
                logger.error("Matrix redact failed (status=%d): %s", resp.status_code, resp.text[:200])
            else:
                self._store_event(target, alert.id, self._REDACTED)
                logger.info("MatrixDelivery: redacted alert %s for %s", alert.id[:8], target)
        except Exception:
            logger.exception("MatrixDelivery redact error for alert %s", alert.id)

    async def redact_for_alert(self, target: str, alert_id: str) -> None:
        target = self._normalize_target(target)
        if self._client is None:
            return
        event_id = self._get_event(target, alert_id)
        if not event_id or event_id == self._REDACTED:
            return
        try:
            room_id = await self._get_or_create_dm_room(target)
        except Exception:
            logger.exception("MatrixDelivery: failed to get room for single redact, target=%s", target)
            return
        txn_id = f"redact-{int(time.time() * 1000)}-{alert_id[:8]}"
        url = f"{self._homeserver}/_matrix/client/v3/rooms/{room_id}/redact/{event_id}/{txn_id}"
        try:
            resp = await self._client.put(url, json={"reason": "alert deleted"})
            if resp.status_code >= 400:
                logger.error("Matrix single redact failed (status=%d): %s", resp.status_code, resp.text[:200])
            else:
                self._store_event(target, alert_id, self._REDACTED)
                logger.info("MatrixDelivery: redacted alert %s for %s", alert_id[:8], target)
        except Exception:
            logger.exception("MatrixDelivery single redact error for alert %s", alert_id)

    async def clear_for_target(self, target: str) -> None:
        target = self._normalize_target(target)
        if self._client is None:
            return
        cache = self._sent_events.get(target)
        if not cache:
            return
        try:
            room_id = await self._get_or_create_dm_room(target)
        except Exception:
            logger.exception("MatrixDelivery: failed to get room for bulk clear, target=%s", target)
            return
        for alert_id, event_id in list(cache.items()):
            if not event_id or event_id == self._REDACTED:
                continue
            txn_id = f"redact-bulk-{int(time.time() * 1000)}-{alert_id[:8]}"
            url = f"{self._homeserver}/_matrix/client/v3/rooms/{room_id}/redact/{event_id}/{txn_id}"
            try:
                resp = await self._client.put(url, json={"reason": "alerts cleared"})
                if resp.status_code >= 400:
                    logger.error("Matrix bulk redact failed (status=%d): %s", resp.status_code, resp.text[:200])
                else:
                    cache[alert_id] = self._REDACTED
            except Exception:
                logger.exception("MatrixDelivery bulk redact error for event %s", event_id)

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
