from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from nexus_portfolio_monitor.detectors.base import Alert

logger = logging.getLogger(__name__)


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


class LoggingAlertDelivery:
    """Stub implementation that logs alerts to console.

    Preserves the existing print-to-console behavior from MonitorService._send_alert.
    Replace with a real backend (e.g. OpenClaw webhook) later.
    """

    async def send_alert(self, alert: Alert) -> None:
        logger.warning(f"Portfolio Alert: {alert.message}")
        print(f"!!!!! Alert !!!!! {alert.ticker} - {alert.kind}")
        print(f"  {alert.message}")
        print(f"  {alert.aggregate.close:,.2f} (Volume {alert.aggregate.volume:,})")
        _print_extra(alert.extra)

    async def connect(self) -> None:
        logger.info("LoggingAlertDelivery connected (no-op)")

    async def disconnect(self) -> None:
        logger.info("LoggingAlertDelivery disconnected (no-op)")


def _print_extra(extra: dict[str, Any], indent: int = 4) -> None:
    prefix = " " * indent
    formatted = "\n".join(
        prefix + line for line in json.dumps(extra, indent=2).splitlines()
    )
    print(formatted)
