from starlette.routing import Route, Router, WebSocketRoute

from portfolio_monitor.service.api.auth import require_admin, require_auth
from portfolio_monitor.service.context import PortfolioMonitorContext

from .routes.accounts import accounts_handler
from .routes.detectors import list_detectors
from .routes.health import health
from .routes.login import login_handler
from .routes.me import me_handler
from .routes.market_info import market_close_handler, market_hours_handler, market_open_handler
from .routes.portfolios import portfolio_handler, portfolios_handler
from .routes.prices import current_price_handler, daily_range_handler, open_close_handler, previous_close_handler, price_history_handler
from .routes.watchlists import watchlists_handler
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

        (
            list_watchlists,
            create_watchlist,
            get_watchlist,
            delete_watchlist,
            add_wl_entry,
            remove_wl_entry,
            update_wl_entry,
            get_wl_entry_alerts,
            update_wl_entry_alerts,
        ) = watchlists_handler(ctx.watchlist_service, ctx.data_provider)

        ws_manager = WebSocketManager(
            bus=ctx.bus,
            session_store=session_store,
            data_provider=ctx.data_provider,
        )
        super().__init__(
            routes=[
                # Public routes — no authentication required
                Route("/health", health, methods=["GET"]),
                Route("/login", login, methods=["POST"]),
                Route("/detectors", list_detectors, methods=["GET"]),
                # Authenticated — any valid session
                Route("/me", require_auth(me), methods=["GET"]),
                Route("/me/alerts", require_auth(get_my_alerts), methods=["GET"]),
                Route("/me/alerts", require_auth(update_my_alerts), methods=["PUT"]),
                Route("/accounts/{username}/password", require_auth(reset_password), methods=["PUT"]),
                Route("/portfolios", require_auth(portfolios_handler(ctx.portfolio_service)), methods=["GET"]),
                Route("/portfolio/{id}", require_auth(portfolio_handler(ctx.portfolio_service)), methods=["GET"]),
                Route("/watchlists", require_auth(list_watchlists), methods=["GET"]),
                Route("/watchlist", require_auth(create_watchlist), methods=["POST"]),
                Route("/watchlist/{id}", require_auth(get_watchlist), methods=["GET"]),
                Route("/watchlist/{id}", require_auth(delete_watchlist), methods=["DELETE"]),
                Route("/watchlist/{id}/entries", require_auth(add_wl_entry), methods=["POST"]),
                Route("/watchlist/{id}/entries/{ticker}", require_auth(remove_wl_entry), methods=["DELETE"]),
                Route("/watchlist/{id}/entries/{ticker}", require_auth(update_wl_entry), methods=["PUT"]),
                Route("/watchlist/{id}/entries/{ticker}/alerts", require_auth(get_wl_entry_alerts), methods=["GET"]),
                Route("/watchlist/{id}/entries/{ticker}/alerts", require_auth(update_wl_entry_alerts), methods=["PUT"]),
                Route("/price/{type}/{ticker}", require_auth(current_price_handler(ctx.data_provider)), methods=["GET"]),
                Route("/price/{type}/{ticker}/previous-close", require_auth(previous_close_handler(ctx.data_provider)), methods=["GET"]),
                Route("/price/{type}/{ticker}/history", require_auth(price_history_handler(ctx.data_provider)), methods=["GET"]),
                Route("/price/{type}/{ticker}/open-close", require_auth(open_close_handler(ctx.data_provider)), methods=["GET"]),
                Route("/price/{type}/{ticker}/daily-range", require_auth(daily_range_handler(ctx.data_provider)), methods=["GET"]),
                Route("/market_info/{type}/{ticker}/hours", market_hours_handler, methods=["GET"]),
                Route("/market_info/{type}/{ticker}/close", market_close_handler, methods=["GET"]),
                Route("/market_info/{type}/{ticker}/open",  market_open_handler,  methods=["GET"]),
                # Admin only
                Route("/accounts", require_admin(list_accounts), methods=["GET"]),
                Route("/accounts", require_admin(create_account), methods=["POST"]),
                Route("/accounts/{username}", require_admin(delete_account), methods=["DELETE"]),
                Route("/accounts/{username}", require_admin(update_account), methods=["PUT"]),
                Route("/accounts/{username}/alerts", require_admin(get_account_alerts), methods=["GET"]),
                Route("/accounts/{username}/alerts", require_admin(update_account_alerts), methods=["PUT"]),
                WebSocketRoute("/ws", ws_manager.handle),
            ]
        )
