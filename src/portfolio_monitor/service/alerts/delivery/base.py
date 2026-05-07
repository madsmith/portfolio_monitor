from __future__ import annotations

from typing import Protocol, runtime_checkable

from portfolio_monitor.detectors import Alert


@runtime_checkable
class AlertDelivery(Protocol):
    """Interface for delivering portfolio alerts to external systems."""

    async def send_alert(self, alert: Alert, *, target: str = "") -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
