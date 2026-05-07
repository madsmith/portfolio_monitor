from portfolio_monitor.account.models import Role
from portfolio_monitor.data.database import AppDatabase

from .models import SessionInfo


class SessionStore:
    """Session CRUD backed by AppDatabase.

    Role is not stored in the sessions table; it is resolved from the accounts
    module on every lookup. The default admin (not in the accounts table) always
    gets admin role. Sessions for deleted accounts are treated as invalid.
    """

    def __init__(self, db: AppDatabase, default_admin_username: str) -> None:
        self._sessions = db.sessions
        self._accounts = db.accounts
        self._default_admin_username: str = default_admin_username

    def create(self, username: str, role: Role) -> str:
        # role accepted for API compatibility but not persisted
        return self._sessions.create(username)

    def get(self, token: str) -> SessionInfo | None:
        record = self._sessions.get(token)
        if record is None:
            return None
        account = self._accounts.get(record.username)
        if account is not None:
            role = Role(account.role)
        elif record.username == self._default_admin_username:
            role = Role.admin
        else:
            # Account deleted after session was created — treat as invalid.
            return None
        return SessionInfo(username=record.username, role=role, created_at=record.created_at)

    def delete(self, token: str) -> None:
        self._sessions.delete(token)
