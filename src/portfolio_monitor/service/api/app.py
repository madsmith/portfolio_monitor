from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.templating import Jinja2Templates

from portfolio_monitor.config import PortfolioMonitorConfig

from .auth import AuthRegistry
from .dashboard import DashboardApp
from .middleware import AuthKeyMiddleware
from .v1 import APIv1ServiceApp

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_api_app(config: PortfolioMonitorConfig) -> Starlette:
    assert config.auth_key is not None, "Auth key is not set"

    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # API sub-app with Bearer token auth
    registry = AuthRegistry()
    api_v1_app = APIv1ServiceApp(registry, prefix="/api/v1")
    api_app = Starlette(
        routes=[Mount("/v1", app=api_v1_app)],
        middleware=[
            Middleware(AuthKeyMiddleware, auth_key=config.auth_key, registry=registry),
        ],
    )

    # Dashboard sub-app with session auth
    dashboard_app = DashboardApp(config=config, templates=templates)

    app = Starlette(
        routes=[
            Mount("/api", app=api_app),
            Mount("/", app=dashboard_app),
        ],
    )
    app.add_middleware(SessionMiddleware, secret_key=config.auth_key)
    return app
