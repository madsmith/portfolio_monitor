from starlette.routing import Route, Router

from .routes.health import health


class APIv1ServiceApp(Router):
    """API v1 application."""

    def __init__(self):
        super().__init__(
            routes=[
                Route("/health", health, methods=["GET"]),
            ]
        )
