from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from portfolio_monitor.detectors import Alert


class AlertEventType(str, Enum):
    FIRED   = "fired"
    UPDATED = "updated"
    CLEARED = "cleared"


@runtime_checkable
class AlertDelivery(Protocol):
    """Interface for delivering portfolio alerts to external systems."""

    async def send_alert(self, alert: Alert, *, target: str = "", event: AlertEventType = AlertEventType.FIRED) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
