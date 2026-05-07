"""DB-backed per-user alert buffer with EventBus-driven push."""
from dataclasses import dataclass
from typing import Any

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database.alerts import AlertRecord, AlertsModule


@dataclass
class AlertBufferEvent:
    """Published on every alert state change for a user.

    The WS manager subscribes to this and forwards the payload to all
    open sockets for the named user.
    """
    username: str
    payload: dict[str, Any]


class AlertBuffer:
    """DB-backed alert store for one user.

    Mutation methods are async because they publish to the EventBus.
    Read methods (get_recent, unread_count) are synchronous DB reads.
    """

    def __init__(self, owner: str, alerts_module: AlertsModule, bus: EventBus) -> None:
        self._owner: str = owner
        self._alerts_module: AlertsModule = alerts_module
        self._bus: EventBus = bus

    @property
    def unread_count(self) -> int:
        return self._alerts_module.get_unread_count(self._owner)

    async def push(self, alert_dict: dict[str, Any]) -> None:
        record, is_new = self._alerts_module.push_record(self._owner, alert_dict)
        if record.deleted:
            return
        await self._bus.publish(AlertBufferEvent(
            username=self._owner,
            payload={
                "event": "fired" if is_new else "updated",
                "alert": self._record_to_dict(record),
                "unread_count": self.unread_count,
            },
        ))

    async def mark_read(self, alert_id: str) -> int:
        count = self._alerts_module.mark_record_read(self._owner, alert_id)
        await self._bus.publish(AlertBufferEvent(
            username=self._owner,
            payload={"event": "read", "alert_id": alert_id, "unread_count": count},
        ))
        return count

    async def mark_all_read(self) -> None:
        self._alerts_module.mark_all_records_read(self._owner)
        await self._bus.publish(AlertBufferEvent(
            username=self._owner,
            payload={"event": "all_read", "unread_count": 0},
        ))

    async def delete(self, alert_id: str) -> int:
        count = self._alerts_module.delete_record(self._owner, alert_id)
        await self._bus.publish(AlertBufferEvent(
            username=self._owner,
            payload={"event": "deleted", "alert_id": alert_id, "unread_count": count},
        ))
        return count

    async def clear(self) -> None:
        self._alerts_module.clear_records(self._owner)
        await self._bus.publish(AlertBufferEvent(
            username=self._owner,
            payload={"event": "cleared", "unread_count": 0},
        ))

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self._record_to_dict(r) for r in self._alerts_module.get_records(self._owner, limit)]

    @staticmethod
    def _record_to_dict(record: AlertRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "ticker": {"ticker": record.ticker, "asset_type": record.asset_type},
            "kind": record.kind,
            "message": record.message,
            "extra": record.extra,
            "at": record.at,
            "updated_at": record.updated_at,
            "read": record.read,
        }


class AlertBufferStore:
    """Holds one AlertBuffer per username, all backed by the same module and bus."""

    def __init__(self, alerts_module: AlertsModule, bus: EventBus) -> None:
        self._alerts_module: AlertsModule = alerts_module
        self._bus: EventBus = bus
        self._buffers: dict[str, AlertBuffer] = {}

    def get_or_create(self, username: str) -> AlertBuffer:
        if username not in self._buffers:
            self._buffers[username] = AlertBuffer(username, self._alerts_module, self._bus)
        return self._buffers[username]

    def get(self, username: str) -> AlertBuffer:
        return self.get_or_create(username)
