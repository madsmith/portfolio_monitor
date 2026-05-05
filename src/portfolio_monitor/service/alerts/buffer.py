"""In-memory per-user alert ring buffer for the dashboard channel."""
import asyncio
from typing import Any


class AlertBuffer:
    """Stores the most recent N alerts for one user and notifies live WS subscribers.

    Alerts are keyed by id so repeated updates to the same ongoing alert update
    in-place rather than appending a duplicate. Each stored entry carries a
    `read` bool that is preserved across updates so the user's read state isn't
    reset when the underlying price moves.

    Queue messages pushed to subscribers are dicts with an `event` key:
      {"event": "fired",   "alert": {..., "read": False}, "unread_count": N}
      {"event": "updated", "alert": {..., "read": bool},  "unread_count": N}
      {"event": "read",    "alert_id": "...",              "unread_count": N}
      {"event": "all_read",                                "unread_count": 0}
      {"event": "cleared",                                 "unread_count": 0}
    """

    MAX_SIZE = 100

    def __init__(self) -> None:
        self._alerts: dict[str, dict[str, Any]] = {}  # id → entry (with read field)
        self._order: list[str] = []  # alert ids, newest first
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    @property
    def unread_count(self) -> int:
        return sum(1 for a in self._alerts.values() if not a.get("read", False))

    def push(self, alert_dict: dict[str, Any]) -> None:
        alert_id = alert_dict["id"]
        if alert_id in self._alerts:
            read = self._alerts[alert_id]["read"]
            self._alerts[alert_id] = {**alert_dict, "read": read}
            event = "updated"
        else:
            if len(self._order) >= self.MAX_SIZE:
                evicted = self._order.pop()
                self._alerts.pop(evicted, None)
            self._order.insert(0, alert_id)
            self._alerts[alert_id] = {**alert_dict, "read": False}
            event = "fired"
        self._broadcast({"event": event, "alert": self._alerts[alert_id], "unread_count": self.unread_count})

    def mark_read(self, alert_id: str) -> int:
        if alert_id in self._alerts:
            self._alerts[alert_id]["read"] = True
        count = self.unread_count
        self._broadcast({"event": "read", "alert_id": alert_id, "unread_count": count})
        return count

    def mark_all_read(self) -> None:
        for a in self._alerts.values():
            a["read"] = True
        self._broadcast({"event": "all_read", "unread_count": 0})

    def clear(self) -> None:
        self._alerts.clear()
        self._order.clear()
        self._broadcast({"event": "cleared", "unread_count": 0})

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self._alerts[aid] for aid in self._order if aid in self._alerts][:limit]

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def _broadcast(self, msg: dict[str, Any]) -> None:
        for q in self._queues:
            q.put_nowait(msg)


class AlertBufferStore:
    """Singleton holding one AlertBuffer per username."""

    def __init__(self) -> None:
        self._buffers: dict[str, AlertBuffer] = {}

    def get_or_create(self, username: str) -> AlertBuffer:
        if username not in self._buffers:
            self._buffers[username] = AlertBuffer()
        return self._buffers[username]

    def get(self, username: str) -> AlertBuffer | None:
        return self._buffers.get(username)
