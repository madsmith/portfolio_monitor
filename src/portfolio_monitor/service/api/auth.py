import hmac

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection


class BearerTokenBackend(AuthenticationBackend):
    """Validates Bearer tokens from the Authorization header.

    Returns a "default" user for valid tokens, or None for
    missing/invalid tokens (leaving the request unauthenticated).
    """

    def __init__(self, auth_key: str):
        self.auth_key: str = auth_key

    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, SimpleUser] | None:
        auth_header = conn.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        if not hmac.compare_digest(token, self.auth_key):
            return None

        return AuthCredentials(["authenticated"]), SimpleUser("default")
