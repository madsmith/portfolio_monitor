from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from portfolio_monitor.service.settings import SessionStore


class SessionBackend(AuthenticationBackend):
    """Validates Bearer tokens against the in-memory session store.

    Returns the session user (with role scope) for valid tokens, or None for
    missing/invalid tokens (leaving the request unauthenticated).
    """

    def __init__(self, session_store: SessionStore) -> None:
        self._session_store: SessionStore = session_store

    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, SimpleUser] | None:
        auth_header = conn.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        session = self._session_store.get(token)
        if session is None:
            return None

        return (
            AuthCredentials(["authenticated", f"role:{session.role}"]),
            SimpleUser(session.username),
        )
