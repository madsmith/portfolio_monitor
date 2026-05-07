import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.account import AccountStore
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.detectors.registry import DetectorRegistry
from portfolio_monitor.service.alerts.models import AlertRule as ServiceAlertRule
from portfolio_monitor.service.alerts.rule_events import AlertRuleAdded, AlertRuleRemoved, AlertRuleUpdated
from portfolio_monitor.session import SessionStore
from portfolio_monitor.utils import logfire_set_attribute


def me_handler(
    account_store: AccountStore,
    session_store: SessionStore,
    default_username: str,
    bus: EventBus,
    alerts_module: AlertsModule,
):
    """Return handlers for /me and /me/alert-config routes."""

    @logfire.instrument("api.me.get")
    async def me(request: Request) -> JSONResponse:
        username = request.user.username
        logfire_set_attribute("username", username)
        role = request.user.role
        return JSONResponse({"username": username, "role": role})

    @logfire.instrument("api.me.alert_config.get")
    async def get_my_alerts(request: Request) -> JSONResponse:
        username = request.user.username
        logfire_set_attribute("username", username)
        db_rules = alerts_module.get_rules(username)
        channels = alerts_module.get_channels(username)
        return JSONResponse({
            "rules": [
                {"id": r.id, "ticker": r.ticker or "", "asset_type": r.asset_type,
                 "kind": r.kind, "args": r.args}
                for r in db_rules
            ],
            "channels": [
                {"id": c.id, "type": c.type, "config": c.config, "enabled": c.enabled}
                for c in channels
            ],
        })

    @logfire.instrument("api.me.alert_config.add_rule")
    async def add_alert_rule(request: Request) -> JSONResponse:
        username = request.user.username
        logfire_set_attribute("username", username)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        ticker = str(body.get("ticker", "")).strip()
        kind = str(body.get("kind", "")).strip()
        args = body.get("args") or {}
        asset_type = body.get("asset_type") or None
        if not kind:
            return JSONResponse({"error": "kind is required"}, status_code=400)
        if DetectorRegistry.get_detector_class(kind) is None:
            return JSONResponse({"error": f"unknown detector kind: {kind}"}, status_code=400)
        db_rule = alerts_module.add_rule(username, ticker or None, asset_type, kind, args)
        service_rule = ServiceAlertRule(id=db_rule.id, ticker=ticker, kind=kind, args=args)
        await bus.publish(AlertRuleAdded(username=username, rule=service_rule))
        return JSONResponse(
            {"id": db_rule.id, "ticker": ticker, "asset_type": asset_type, "kind": kind, "args": args},
            status_code=201,
        )

    @logfire.instrument("api.me.alert_config.update_rule")
    async def update_alert_rule(request: Request) -> JSONResponse:
        username = request.user.username
        rule_id = request.path_params["rule_id"]
        logfire_set_attribute("username", username)
        existing = alerts_module.get_rule(rule_id)
        if existing is None or existing.owner != username:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        new_args = body.get("args", existing.args)
        alerts_module.update_rule(rule_id, new_args)
        old_rule = ServiceAlertRule(id=existing.id, ticker=existing.ticker or "", kind=existing.kind, args=existing.args)
        new_rule = ServiceAlertRule(id=existing.id, ticker=existing.ticker or "", kind=existing.kind, args=new_args)
        await bus.publish(AlertRuleUpdated(username=username, old_rule=old_rule, new_rule=new_rule))
        return JSONResponse({"id": rule_id, "args": new_args})

    @logfire.instrument("api.me.alert_config.delete_rule")
    async def delete_alert_rule(request: Request) -> JSONResponse:
        username = request.user.username
        rule_id = request.path_params["rule_id"]
        logfire_set_attribute("username", username)
        existing = alerts_module.get_rule(rule_id)
        if existing is None or existing.owner != username:
            return JSONResponse({"error": "not found"}, status_code=404)
        alerts_module.delete_rule(rule_id, username)
        service_rule = ServiceAlertRule(
            id=existing.id, ticker=existing.ticker or "", kind=existing.kind, args=existing.args
        )
        await bus.publish(AlertRuleRemoved(username=username, rule=service_rule))
        return JSONResponse({"ok": True})

    @logfire.instrument("api.me.alert_config.add_channel")
    async def add_alert_channel(request: Request) -> JSONResponse:
        username = request.user.username
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        ch_type = str(body.get("type", "")).strip()
        config = body.get("config") or {}
        enabled = bool(body.get("enabled", True))
        if not ch_type:
            return JSONResponse({"error": "type is required"}, status_code=400)
        ch = alerts_module.upsert_channel(username, ch_type, config, enabled)
        return JSONResponse({"id": ch.id, "type": ch.type, "config": ch.config, "enabled": ch.enabled}, status_code=201)

    @logfire.instrument("api.me.alert_config.update_channel")
    async def update_alert_channel(request: Request) -> JSONResponse:
        username = request.user.username
        channel_id = int(request.path_params["channel_id"])
        owned = {c.id for c in alerts_module.get_channels(username)}
        if channel_id not in owned:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        config = body.get("config", {})
        enabled = bool(body.get("enabled", True))
        alerts_module.update_channel(channel_id, config, enabled)
        return JSONResponse({"ok": True})

    @logfire.instrument("api.me.alert_config.delete_channel")
    async def delete_alert_channel(request: Request) -> JSONResponse:
        username = request.user.username
        channel_id = int(request.path_params["channel_id"])
        owned = {c.id for c in alerts_module.get_channels(username)}
        if channel_id not in owned:
            return JSONResponse({"error": "not found"}, status_code=404)
        alerts_module.delete_channel(channel_id)
        return JSONResponse({"ok": True})

    return (
        me,
        get_my_alerts,
        add_alert_rule,
        update_alert_rule,
        delete_alert_rule,
        add_alert_channel,
        update_alert_channel,
        delete_alert_channel,
    )
