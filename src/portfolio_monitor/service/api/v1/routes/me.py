import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.service.alerts.models import AlertRule, UserAlertConfig
from portfolio_monitor.service.alerts.rule_events import AlertRuleAdded, AlertRuleRemoved, AlertRuleUpdated
from portfolio_monitor.service.settings import AccountStore, SessionStore
from portfolio_monitor.utils import logfire_set_attribute


def me_handler(account_store: AccountStore, session_store: SessionStore, default_username: str, bus: EventBus):
    """Return handlers for /me, /me/alert-config, and /me/alert-config/rules."""

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

    @logfire.instrument("api.me.alert_config.add_rule")
    async def add_alert_rule(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        ticker = body.get("ticker", "")
        kind = body.get("kind", "")
        args = body.get("args") or {}
        if not kind:
            return JSONResponse({"error": "kind is required"}, status_code=400)
        username = request.user.display_name
        logfire_set_attribute("username", username)
        config = _get_alert_config(username, account_store, default_username)
        rule = AlertRule.create(ticker=ticker, kind=kind, args=args)
        config.rules.append(rule)
        _set_alert_config(username, config, account_store, default_username)
        account_store.save()
        await bus.publish(AlertRuleAdded(username=username, rule=rule))
        return JSONResponse(rule.to_dict(), status_code=201)

    @logfire.instrument("api.me.alert_config.update_rule")
    async def update_alert_rule(request: Request) -> JSONResponse:
        rule_id = request.path_params["rule_id"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        username = request.user.display_name
        logfire_set_attribute("username", username)
        config = _get_alert_config(username, account_store, default_username)
        rule = next((r for r in config.rules if r.id == rule_id), None)
        if rule is None:
            return JSONResponse({"error": "rule not found"}, status_code=404)
        old_rule = AlertRule.from_dict(rule.to_dict())
        if "args" in body:
            rule.args = body["args"]
        if "ticker" in body:
            rule.ticker = body["ticker"]
        if "kind" in body:
            rule.kind = body["kind"]
        _set_alert_config(username, config, account_store, default_username)
        account_store.save()
        await bus.publish(AlertRuleUpdated(username=username, old_rule=old_rule, new_rule=rule))
        return JSONResponse(rule.to_dict())

    @logfire.instrument("api.me.alert_config.delete_rule")
    async def delete_alert_rule(request: Request) -> JSONResponse:
        rule_id = request.path_params["rule_id"]
        username = request.user.display_name
        logfire_set_attribute("username", username)
        config = _get_alert_config(username, account_store, default_username)
        rule = next((r for r in config.rules if r.id == rule_id), None)
        if rule is None:
            return JSONResponse({"error": "rule not found"}, status_code=404)
        config.delete_rule(rule_id)
        _set_alert_config(username, config, account_store, default_username)
        account_store.save()
        await bus.publish(AlertRuleRemoved(username=username, rule=rule))
        return JSONResponse({"ok": True})

    return me, get_my_alerts, update_my_alerts, add_alert_rule, update_alert_rule, delete_alert_rule


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
