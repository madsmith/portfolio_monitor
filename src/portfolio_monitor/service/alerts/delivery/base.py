from __future__ import annotations

from typing import Protocol, runtime_checkable

from portfolio_monitor.detectors.base import Alert


@runtime_checkable
class AlertDelivery(Protocol):
    """Interface for delivering portfolio alerts to external systems.

    Current method:
        send_alert -- deliver a triggered detector alert

    Future methods (to be implemented when needed):
        subscribe_webhook -- register a webhook endpoint for alert delivery
        query_portfolio   -- respond to external queries about portfolio state
    """

    async def send_alert(self, alert: Alert) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
