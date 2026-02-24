from starlette.routing import Route, Router

from portfolio_monitor.service.api.auth import AuthRegistry

from .routes.health import health


class APIv1ServiceApp(Router):
    """API v1 application. Registers its public routes with the auth registry."""

    PUBLIC_PATHS = ["/health"]

    def __init__(self, registry: AuthRegistry, prefix: str = ""):
        super().__init__(
            routes=[
                Route("/health", health, methods=["GET"]),
            ]
        )

        # Register public paths with the auth registry
        for path in self.PUBLIC_PATHS:
            registry.add_public_path(f"{prefix}{path}")
