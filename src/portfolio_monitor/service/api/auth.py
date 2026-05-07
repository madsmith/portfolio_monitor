from collections.abc import Callable, Coroutine
from typing import Any

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    BaseUser,
)
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse, Response

from portfolio_monitor.session import SessionStore

Handler = Callable[[Request], Coroutine[Any, Any, Response]]


class PortfolioUser(BaseUser):
    """Authenticated user with username and role, available via request.user."""

    def __init__(self, username: str, role: str) -> None:
        self.username: str = username
        self.role: str = role

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self.username


def require_auth(handler: Handler) -> Handler:
    """Route wrapper: reject unauthenticated requests with 401."""
    async def _wrapper(request: Request) -> Response:
        if not request.user.is_authenticated:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await handler(request)
    return _wrapper


def require_admin(handler: Handler) -> Handler:
    """Route wrapper: reject unauthenticated requests with 401, non-admin with 403."""
    async def _wrapper(request: Request) -> Response:
        if not request.user.is_authenticated:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not isinstance(request.user, PortfolioUser) or request.user.role != "admin":
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return await handler(request)
    return _wrapper


class SessionBackend(AuthenticationBackend):
    """Validates Bearer tokens against the in-memory session store.

    Returns the session user (with role scope) for valid tokens, or None for
    missing/invalid tokens (leaving the request unauthenticated).
    """

    def __init__(self, session_store: SessionStore) -> None:
        self._session_store: SessionStore = session_store

    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, PortfolioUser] | None:
        auth_header = conn.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        session = self._session_store.get(token)
        if session is None:
            return None

        return (
            AuthCredentials(["authenticated", f"role:{session.role}"]),
            PortfolioUser(session.username, str(session.role)),
        )
