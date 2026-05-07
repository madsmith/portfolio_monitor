from dataclasses import dataclass
from datetime import datetime

from portfolio_monitor.account.models import Role


@dataclass
class SessionInfo:
    username: str
    role: Role
    created_at: datetime
