from starlette.routing import Route, Router

from portfolio_monitor.config import PortfolioMonitorConfig

from .routes.health import health
from .routes.login import make_login_handler


class APIv1ServiceApp(Router):
    """API v1 application."""

    def __init__(self, config: PortfolioMonitorConfig):
        assert config.auth_key, "auth_key is required"
        assert config.dashboard_username, "dashboard_username is required"
        assert config.dashboard_password, "dashboard_password is required"
        login = make_login_handler(
            config.auth_key,
            config.dashboard_username,
            config.dashboard_password,
        )
        super().__init__(
            routes=[
                Route("/health", health, methods=["GET"]),
                Route("/login", login, methods=["POST"]),
            ]
        )
