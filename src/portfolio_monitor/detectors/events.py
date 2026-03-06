from dataclasses import dataclass

from portfolio_monitor.detectors.base import Alert


@dataclass
class AlertFired:
    """A detector triggered a new alert."""

    alert: Alert


@dataclass
class AlertUpdated:
    """An existing alert was updated with new data (same occurrence, same id)."""

    alert: Alert


@dataclass
class AlertCleared:
    """An active alert condition ended."""

    alert: Alert
