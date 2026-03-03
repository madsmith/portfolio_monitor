from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount

from portfolio_monitor.service.context import PortfolioMonitorContext

from ..dashboard import DashboardApp
from .auth import BearerTokenBackend
from .v1 import APIv1ServiceApp


def create_api_app(ctx: PortfolioMonitorContext) -> Starlette:
    assert ctx.config.auth_key, "auth_key is required"

    # API sub-app with Bearer token auth
    api_v1_app = APIv1ServiceApp(ctx)
    api_app = Starlette(
        routes=[Mount("/v1", app=api_v1_app)],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=BearerTokenBackend(ctx.config.auth_key),
            ),
        ],
    )

    # Dashboard sub-app — serves React SPA
    dashboard_app = DashboardApp()

    return Starlette(
        routes=[
            Mount("/api", app=api_app),
            Mount("/", app=dashboard_app),
        ],
    )
