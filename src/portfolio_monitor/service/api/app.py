from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount

from portfolio_monitor.service.context import PortfolioMonitorContext

from ..dashboard import DashboardApp
from .auth import SessionBackend
from .v1 import APIv1ServiceApp


def create_api_app(ctx: PortfolioMonitorContext) -> Starlette:
    # API sub-app with session-based Bearer token auth
    api_v1_app = APIv1ServiceApp(ctx)
    api_app = Starlette(
        routes=[Mount("/v1", app=api_v1_app)],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=SessionBackend(ctx.session_store),
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
