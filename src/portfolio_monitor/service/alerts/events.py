from dataclasses import dataclass
from typing import Any

from portfolio_monitor.service.alerts.models import AlertRule


@dataclass
class AlertStatusEvent:
    """Published on every alert state change for a user.

    The WS manager subscribes to this and forwards the payload to all
    open sockets for the named user.
    """
    username: str
    payload: dict[str, Any]


@dataclass
class UserAlertDeletedEvent:
    """Published when a user deletes a single alert."""
    username: str
    alert_id: str


@dataclass
class UserAlertsClearedEvent:
    """Published when a user clears all their alerts."""
    username: str


@dataclass
class AlertRuleAdded:
    """A new alert rule was saved for a user."""
    username: str
    rule: AlertRule


@dataclass
class AlertRuleRemoved:
    """An alert rule was deleted for a user."""
    username: str
    rule: AlertRule  # the rule as it was before deletion


@dataclass
class AlertRuleUpdated:
    """An existing alert rule was modified."""
    username: str
    old_rule: AlertRule
    new_rule: AlertRule
