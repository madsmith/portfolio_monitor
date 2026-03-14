import secrets
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Role


@dataclass
class SessionInfo:
    username: str
    role: Role
    created_at: datetime


class SessionStore:
    """File-backed session store mapping bearer tokens to authenticated sessions.

    Sessions are persisted to a YAML file and survive process restarts.
    """

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._sessions: dict[str, SessionInfo] = {}

    def load(self) -> None:
        if not self._path.exists():
            self._sessions = {}
            return
        with self._path.open() as f:
            data = yaml.safe_load(f) or {}
        self._sessions = {
            token: SessionInfo(
                username=info["username"],
                role=Role(info["role"]),
                created_at=datetime.fromisoformat(info["created_at"]),
            )
            for token, info in data.items()
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            token: {
                "username": info.username,
                "role": str(info.role),
                "created_at": info.created_at.isoformat(),
            }
            for token, info in self._sessions.items()
        }
        with self._path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def create(self, username: str, role: Role) -> str:
        token = secrets.token_hex(32)
        self._sessions[token] = SessionInfo(
            username=username,
            role=role,
            created_at=datetime.now(timezone.utc),
        )
        self._save()
        return token

    def get(self, token: str) -> SessionInfo | None:
        return self._sessions.get(token)

    def delete(self, token: str) -> None:
        self._sessions.pop(token, None)
        self._save()
