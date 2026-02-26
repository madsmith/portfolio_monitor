from __future__ import annotations

import json
from typing import Any

from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.utils import get_trace_logger

logger = get_trace_logger(__name__)


class LoggingAlertDelivery:
    """Stub implementation that logs alerts to console.

    Preserves the existing print-to-console behavior from MonitorService._send_alert.
    Replace with a real backend (e.g. OpenClaw webhook) later.
    """

    async def send_alert(self, alert: Alert) -> None:
        logger.trace(f"Portfolio Alert: {alert.message}")
        return
        # Short circuit debug logic for now
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
