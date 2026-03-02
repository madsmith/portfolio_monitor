from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.templating import Jinja2Templates

from ..dashboard import DashboardApp
from .auth import BearerTokenBackend
from .v1 import APIv1ServiceApp

TEMPLATES_DIR = Path(__file__).parent.parent / "dashboard" / "templates"


def create_api_app(
    auth_key: str, dashboard_username: str, dashboard_password: str
) -> Starlette:
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # API sub-app with Bearer token auth
    api_v1_app = APIv1ServiceApp()
    api_app = Starlette(
        routes=[Mount("/v1", app=api_v1_app)],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=BearerTokenBackend(auth_key),
            ),
        ],
    )

    # Dashboard sub-app with session auth
    dashboard_app = DashboardApp(
        username=dashboard_username,
        password=dashboard_password,
        templates=templates,
    )

    app = Starlette(
        routes=[
            Mount("/api", app=api_app),
            Mount("/", app=dashboard_app),
        ],
    )
    app.add_middleware(SessionMiddleware, secret_key=auth_key)

    return app
