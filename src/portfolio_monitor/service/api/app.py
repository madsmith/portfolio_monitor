from starlette.applications import Starlette
from starlette.routing import Mount

from .auth import AuthRegistry
from .middleware import AuthKeyMiddleware
from .v1 import APIv1ServiceApp


def create_api_app(auth_key: str) -> Starlette:
    registry = AuthRegistry()
    api_v1_app = APIv1ServiceApp(registry, prefix="/api/v1")

    app = Starlette(
        routes=[
            Mount(
                "/api",
                routes=[
                    Mount("/v1", app=api_v1_app),
                ],
            ),
        ],
    )
    app.add_middleware(AuthKeyMiddleware, auth_key=auth_key, registry=registry)
    return app
