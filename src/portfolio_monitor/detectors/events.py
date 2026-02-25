from dataclasses import dataclass

from portfolio_monitor.detectors.base import Alert


@dataclass
class AlertFired:
    """A detector triggered an alert."""

    alert: Alert
