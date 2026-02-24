from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.templating import Jinja2Templates

from portfolio_monitor.config import PortfolioMonitorConfig

from .auth import BearerTokenBackend
from .dashboard import DashboardApp
from .v1 import APIv1ServiceApp

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_api_app(config: PortfolioMonitorConfig) -> Starlette:
    assert config.auth_key is not None, "Auth key is not set"

    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # API sub-app with Bearer token auth
    api_v1_app = APIv1ServiceApp()
    api_app = Starlette(
        routes=[Mount("/v1", app=api_v1_app)],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=BearerTokenBackend(config),
            ),
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
