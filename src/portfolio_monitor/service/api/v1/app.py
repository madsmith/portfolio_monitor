from starlette.routing import Route, Router, WebSocketRoute

from portfolio_monitor.service.context import PortfolioMonitorContext

from .routes.accounts import accounts_handler
from .routes.health import health
from .routes.login import login_handler
from .routes.me import me_handler
from .routes.portfolios import portfolio_handler, portfolios_handler
from .routes.prices import current_price_handler, previous_close_handler, price_history_handler
from .ws import WebSocketManager


class APIv1ServiceApp(Router):
    """API v1 application."""

    def __init__(self, ctx: PortfolioMonitorContext):
        config = ctx.config
        account_store = ctx.account_store
        session_store = ctx.session_store

        assert config.dashboard_username is not None, "dashboard_username must be set in config"
        assert config.dashboard_password is not None, "dashboard_password must be set in config"

        login = login_handler(
            account_store,
            session_store,
            config.dashboard_username,
            config.dashboard_password,
        )
        me, get_my_alerts, update_my_alerts = me_handler(
            account_store, session_store, config.dashboard_username
        )
        (
            list_accounts,
            create_account,
            delete_account,
            update_account,
            reset_password,
            get_account_alerts,
            update_account_alerts,
        ) = accounts_handler(account_store, session_store, config.dashboard_username)

        ws_manager = WebSocketManager(
            bus=ctx.bus,
            session_store=session_store,
            data_provider=ctx.data_provider,
        )
        super().__init__(
            routes=[
                Route("/health", health, methods=["GET"]),
                Route("/login", login, methods=["POST"]),
                Route("/me", me, methods=["GET"]),
                Route("/me/alerts", get_my_alerts, methods=["GET"]),
                Route("/me/alerts", update_my_alerts, methods=["PUT"]),
                Route("/accounts", list_accounts, methods=["GET"]),
                Route("/accounts", create_account, methods=["POST"]),
                Route("/accounts/{username}", delete_account, methods=["DELETE"]),
                Route("/accounts/{username}", update_account, methods=["PUT"]),
                Route("/accounts/{username}/password", reset_password, methods=["PUT"]),
                Route("/accounts/{username}/alerts", get_account_alerts, methods=["GET"]),
                Route("/accounts/{username}/alerts", update_account_alerts, methods=["PUT"]),
                Route("/portfolios", portfolios_handler(ctx.portfolio_service), methods=["GET"]),
                Route("/portfolio/{id}", portfolio_handler(ctx.portfolio_service), methods=["GET"]),
                Route("/price/{type}/{ticker}", current_price_handler(ctx.data_provider), methods=["GET"]),
                Route("/price/{type}/{ticker}/previous-close", previous_close_handler(ctx.data_provider), methods=["GET"]),
                Route("/price/{type}/{ticker}/history", price_history_handler(ctx.data_provider), methods=["GET"]),
                WebSocketRoute("/ws", ws_manager.handle),
            ]
        )
