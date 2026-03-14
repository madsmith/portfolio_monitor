from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    admin = "admin"
    normal = "normal"


@dataclass
class Account:
    username: str
    password_hash: str
    role: Role
    alerts: dict[str, Any] = field(default_factory=dict)
