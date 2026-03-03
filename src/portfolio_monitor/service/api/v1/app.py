from starlette.routing import Route, Router, WebSocketRoute

from portfolio_monitor.service.context import PortfolioMonitorContext

from .routes.health import health
from .routes.login import login_handler
from .routes.portfolios import portfolio_handler, portfolios_handler
from .ws import WebSocketManager


class APIv1ServiceApp(Router):
    """API v1 application."""

    def __init__(self, ctx: PortfolioMonitorContext):
        config = ctx.config
        assert config.auth_key, "auth_key is required"
        assert config.dashboard_username, "dashboard_username is required"
        assert config.dashboard_password, "dashboard_password is required"
        login = login_handler(
            config.auth_key,
            config.dashboard_username,
            config.dashboard_password,
        )
        ws_manager = WebSocketManager(bus=ctx.bus, auth_key=config.auth_key)
        super().__init__(
            routes=[
                Route("/health", health, methods=["GET"]),
                Route("/login", login, methods=["POST"]),
                Route("/portfolios", portfolios_handler(ctx.portfolio_service), methods=["GET"]),
                Route("/portfolio/{id}", portfolio_handler(ctx.portfolio_service), methods=["GET"]),
                WebSocketRoute("/ws", ws_manager.handle),
            ]
        )
