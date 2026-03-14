import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.service.settings import AccountStore, Role, SessionStore


def login_handler(
    account_store: AccountStore,
    session_store: SessionStore,
    default_username: str,
    default_password: str,
):
    """Return a login route handler that validates against the account store and the default admin."""

    async def login(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)

        req_username = str(data.get("username", ""))
        req_password = str(data.get("password", ""))

        # Check default admin credentials (constant-time comparison)
        is_default_admin = hmac.compare_digest(req_username, default_username) and hmac.compare_digest(
            req_password, default_password
        )
        if is_default_admin:
            token = session_store.create(req_username, Role.admin)
            return JSONResponse({"token": token, "username": req_username, "role": str(Role.admin)})

        # Check named accounts
        account = account_store.verify(req_username, req_password)
        if account is not None:
            token = session_store.create(account.username, account.role)
            return JSONResponse({"token": token, "username": account.username, "role": str(account.role)})

        return JSONResponse({"error": "invalid credentials"}, status_code=401)

    return login
