import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse


def make_login_handler(auth_key: str, username: str, password: str):
    """Return a login route handler closed over the server credentials."""

    async def login(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)

        req_username = data.get("username", "")
        req_password = data.get("password", "")

        valid = hmac.compare_digest(
            str(req_username), username
        ) and hmac.compare_digest(str(req_password), password)

        if not valid:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)

        return JSONResponse({"token": auth_key})

    return login
