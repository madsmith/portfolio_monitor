from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    normal = "normal"


@dataclass
class Account:
    username: str
    password_hash: str
    role: Role
