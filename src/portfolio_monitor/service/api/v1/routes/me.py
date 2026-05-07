import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.account import AccountStore
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.detectors.registry import DetectorRegistry
from portfolio_monitor.service.alerts.models import AlertRule as ServiceAlertRule
from portfolio_monitor.service.alerts.events import AlertRuleAdded, AlertRuleRemoved, AlertRuleUpdated
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
        subs = alerts_module.get_subscriptions(username)
        sub_list = []
        for sub in subs:
            cfg = alerts_module.get_channel_config(sub.channel_config_id)
            sub_list.append({
                "id": sub.id,
                "channel_config_id": sub.channel_config_id,
                "channel_name": cfg.name if cfg else "",
                "channel_type": cfg.type if cfg else "",
                "target": sub.target,
                "mode": sub.mode,
            })
        return JSONResponse({
            "rules": [
                {"id": r.id, "ticker": r.ticker or "", "asset_type": r.asset_type,
                 "kind": r.kind, "args": r.args}
                for r in db_rules
            ],
            "subscriptions": sub_list,
        })

    @logfire.instrument("api.me.alert_config.available_channels")
    async def list_available_channels(request: Request) -> JSONResponse:
        configs = alerts_module.get_all_channel_configs()
        return JSONResponse([
            {"id": c.id, "type": c.type, "name": c.name}
            for c in configs
        ])

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

    @logfire.instrument("api.me.alert_config.add_subscription")
    async def add_subscription(request: Request) -> JSONResponse:
        username = request.user.username
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        channel_config_id = str(body.get("channel_config_id", "")).strip()
        target = str(body.get("target", "")).strip()
        mode = str(body.get("mode", "default")).strip()
        if not channel_config_id:
            return JSONResponse({"error": "channel_config_id is required"}, status_code=400)
        if alerts_module.get_channel_config(channel_config_id) is None:
            return JSONResponse({"error": "channel config not found"}, status_code=404)
        if mode not in ("off", "default", "opt_in"):
            return JSONResponse({"error": "mode must be off, default, or opt_in"}, status_code=400)
        sub = alerts_module.add_subscription(username, channel_config_id, target, mode)
        cfg = alerts_module.get_channel_config(channel_config_id)
        return JSONResponse({
            "id": sub.id,
            "channel_config_id": sub.channel_config_id,
            "channel_name": cfg.name if cfg else "",
            "channel_type": cfg.type if cfg else "",
            "target": sub.target,
            "mode": sub.mode,
        }, status_code=201)

    @logfire.instrument("api.me.alert_config.update_subscription")
    async def update_subscription(request: Request) -> JSONResponse:
        username = request.user.username
        sub_id = request.path_params["sub_id"]
        existing = alerts_module.get_subscription(sub_id)
        if existing is None or existing.owner != username:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        target = str(body.get("target", existing.target)).strip()
        mode = str(body.get("mode", existing.mode)).strip()
        if mode not in ("off", "default", "opt_in"):
            return JSONResponse({"error": "mode must be off, default, or opt_in"}, status_code=400)
        alerts_module.update_subscription(sub_id, target, mode)
        return JSONResponse({"ok": True})

    @logfire.instrument("api.me.alert_config.delete_subscription")
    async def delete_subscription(request: Request) -> JSONResponse:
        username = request.user.username
        sub_id = request.path_params["sub_id"]
        existing = alerts_module.get_subscription(sub_id)
        if existing is None or existing.owner != username:
            return JSONResponse({"error": "not found"}, status_code=404)
        alerts_module.delete_subscription(sub_id, username)
        return JSONResponse({"ok": True})

    return (
        me,
        get_my_alerts,
        list_available_channels,
        add_alert_rule,
        update_alert_rule,
        delete_alert_rule,
        add_subscription,
        update_subscription,
        delete_subscription,
    )
