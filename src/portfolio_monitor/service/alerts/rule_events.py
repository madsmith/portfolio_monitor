from dataclasses import dataclass

from portfolio_monitor.service.alerts.models import AlertRule


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
