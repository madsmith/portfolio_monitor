from dataclasses import dataclass, field
from enum import StrEnum

from portfolio_monitor.service.alerts.models import UserAlertConfig


class Role(StrEnum):
    admin = "admin"
    normal = "normal"


@dataclass
class Account:
    username: str
    password_hash: str
    role: Role
    alert_config: UserAlertConfig = field(default_factory=UserAlertConfig)
