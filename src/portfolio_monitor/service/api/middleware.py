import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .auth import AuthRegistry


class AuthKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, auth_key: str, registry: AuthRegistry):
        super().__init__(app)
        self.auth_key: str = auth_key
        self.registry: AuthRegistry = registry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.registry.is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "unauthorized",
                    "message": "Missing or invalid authorization header",
                },
                status_code=401,
            )

        token = auth_header[7:]
        if not hmac.compare_digest(token, self.auth_key):
            return JSONResponse(
                {"error": "unauthorized", "message": "Invalid authorization token"},
                status_code=401,
            )

        return await call_next(request)
