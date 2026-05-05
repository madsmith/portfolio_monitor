import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.service.alerts.models import UserAlertConfig
from portfolio_monitor.service.settings import AccountStore, SessionStore
from portfolio_monitor.utils import logfire_set_attribute


def me_handler(account_store: AccountStore, session_store: SessionStore, default_username: str):
    """Return handlers for /me and /me/alert-config."""

    @logfire.instrument("api.me.get")
    async def me(request: Request) -> JSONResponse:
        username = request.user.display_name
        logfire_set_attribute("username", username)
        role = _role_from_scopes(request.auth.scopes)
        return JSONResponse({"username": username, "role": role})

    @logfire.instrument("api.me.alert_config.get")
    async def get_my_alerts(request: Request) -> JSONResponse:
        username = request.user.display_name
        logfire_set_attribute("username", username)
        config = _get_alert_config(username, account_store, default_username)
        return JSONResponse(config.to_dict())

    @logfire.instrument("api.me.alert_config.update")
    async def update_my_alerts(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        username = request.user.display_name
        logfire_set_attribute("username", username)
        config = UserAlertConfig.from_dict(body)
        _set_alert_config(username, config, account_store, default_username)
        account_store.save()
        return JSONResponse({"ok": True})

    return me, get_my_alerts, update_my_alerts


def _role_from_scopes(scopes: list[str]) -> str:
    for scope in scopes:
        if scope.startswith("role:"):
            return scope[5:]
    return "normal"


def _get_alert_config(username: str, account_store: AccountStore, default_username: str) -> UserAlertConfig:
    if username == default_username:
        return account_store.get_default_admin_alert_config()
    account = account_store.get(username)
    return account.alert_config if account else UserAlertConfig()


def _set_alert_config(username: str, config: UserAlertConfig, account_store: AccountStore, default_username: str) -> None:
    if username == default_username:
        account_store.set_default_admin_alert_config(config)
    else:
        account_store.update_alert_config(username, config)
