"""In-memory per-user alert ring buffer for the dashboard channel."""
import asyncio
from collections import deque
from typing import Any


class AlertBuffer:
    """Stores the most recent N alerts for one user and notifies live WS subscribers."""

    MAX_SIZE = 100

    def __init__(self) -> None:
        self._alerts: deque[dict[str, Any]] = deque(maxlen=self.MAX_SIZE)
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    def push(self, alert_dict: dict[str, Any]) -> None:
        self._alerts.appendleft(alert_dict)
        for q in self._queues:
            q.put_nowait(alert_dict)

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._alerts)[:limit]

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass


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
