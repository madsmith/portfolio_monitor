import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.service.settings import AccountStore, SessionStore
from portfolio_monitor.utils import logfire_set_attribute


def me_handler(account_store: AccountStore, session_store: SessionStore, default_username: str):
    """Return handlers for /me and /me/alerts."""

    @logfire.instrument("api.me.get")
    async def me(request: Request) -> JSONResponse:
        username = request.user.display_name
        logfire_set_attribute("username", username)
        role = _role_from_scopes(request.auth.scopes)
        return JSONResponse({"username": username, "role": role})

    @logfire.instrument("api.me.alerts.get")
    async def get_my_alerts(request: Request) -> JSONResponse:
        username = request.user.display_name
        logfire_set_attribute("username", username)
        alerts = _get_alerts(username, account_store, default_username)
        return JSONResponse(alerts)

    @logfire.instrument("api.me.alerts.update")
    async def update_my_alerts(request: Request) -> JSONResponse:
        try:
            alerts = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        username = request.user.display_name
        logfire_set_attribute("username", username)
        _set_alerts(username, alerts, account_store, default_username)
        account_store.save()
        return JSONResponse({"ok": True})

    return me, get_my_alerts, update_my_alerts


def _role_from_scopes(scopes: list[str]) -> str:
    for scope in scopes:
        if scope.startswith("role:"):
            return scope[5:]
    return "normal"


def _get_alerts(username: str, account_store: AccountStore, default_username: str) -> dict:
    if username == default_username:
        return account_store.get_default_admin_alerts()
    account = account_store.get(username)
    return account.alerts if account else {}


def _set_alerts(username: str, alerts: dict, account_store: AccountStore, default_username: str) -> None:
    if username == default_username:
        account_store.set_default_admin_alerts(alerts)
    else:
        account_store.update_alerts(username, alerts)
