import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.utils import logfire_set_attribute


def admin_channels_handler(alerts_module: AlertsModule):
    """Return CRUD handlers for /admin/alert-channel-configs routes (admin-only)."""

    @logfire.instrument("api.admin.channel_configs.list")
    async def list_channel_configs(request: Request) -> JSONResponse:
        configs = alerts_module.get_all_channel_configs()
        return JSONResponse([
            {"id": c.id, "type": c.type, "name": c.name, "config": c.config}
            for c in configs
        ])

    @logfire.instrument("api.admin.channel_configs.create")
    async def create_channel_config(request: Request) -> JSONResponse:
        logfire_set_attribute("username", request.user.username)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        ch_type = str(body.get("type", "")).strip()
        name = str(body.get("name", "")).strip()
        config = body.get("config") or {}
        if not ch_type:
            return JSONResponse({"error": "type is required"}, status_code=400)
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)
        cfg = alerts_module.add_channel_config(ch_type, name, config)
        return JSONResponse(
            {"id": cfg.id, "type": cfg.type, "name": cfg.name, "config": cfg.config},
            status_code=201,
        )

    @logfire.instrument("api.admin.channel_configs.update")
    async def update_channel_config(request: Request) -> JSONResponse:
        logfire_set_attribute("username", request.user.username)
        cfg_id = request.path_params["cfg_id"]
        existing = alerts_module.get_channel_config(cfg_id)
        if existing is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request body"}, status_code=400)
        name = str(body.get("name", existing.name)).strip() or existing.name
        config = body.get("config", existing.config)
        alerts_module.update_channel_config(cfg_id, name, config)
        return JSONResponse({"ok": True})

    @logfire.instrument("api.admin.channel_configs.delete")
    async def delete_channel_config(request: Request) -> JSONResponse:
        logfire_set_attribute("username", request.user.username)
        cfg_id = request.path_params["cfg_id"]
        if not alerts_module.delete_channel_config(cfg_id):
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"ok": True})

    return list_channel_configs, create_channel_config, update_channel_config, delete_channel_config
