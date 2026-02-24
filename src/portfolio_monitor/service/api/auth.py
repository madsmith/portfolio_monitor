import hmac

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from portfolio_monitor.config import PortfolioMonitorConfig


class BearerTokenBackend(AuthenticationBackend):
    """Validates Bearer tokens from the Authorization header.

    Returns a "default" user for valid tokens, or None for
    missing/invalid tokens (leaving the request unauthenticated).
    """

    def __init__(self, config: PortfolioMonitorConfig):
        assert config.auth_key is not None, "auth_key must be set"
        self.auth_key: str = config.auth_key

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
