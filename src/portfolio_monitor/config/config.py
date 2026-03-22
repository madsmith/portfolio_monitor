from pathlib import Path
from typing import Any

from appconf import AppConfig, Bind, BindDefault


class PortfolioMonitorConfig(AppConfig):
    """Typed configuration for the Portfolio Monitor application."""

    portfolio_path = Bind[Path](
        "portfolio_monitor.portfolio_path",
        converter=Path,
    )
    watchlist_path = BindDefault[Path](
        "portfolio_monitor.watchlist_path",
        default="./config/watchlists",
        converter=Path,
    )
    aggregate_cache_path = BindDefault[Path](
        "portfolio_monitor.aggregate_cache_path",
        default="./config/aggregate_cache.db",
        converter=Path,
    )
    settings_path = BindDefault[Path](
        "portfolio_monitor.settings_path",
        default="./config/settings.yaml",
        converter=Path,
    )
    session_store_path = BindDefault[Path](
        "portfolio_monitor.session_store_path",
        default="./config/sessions.yaml",
        converter=Path,
    )

    # Polygon.io settings
    polygon_api_key = Bind[str]("polygon.api_key")
    polygon_delay = BindDefault[int]("polygon.delay", default=15 * 60)
    polygon_prime_limit = BindDefault[int]("polygon.prime_limit", default=120)

    # Control interface settings
    host = BindDefault[str]("portfolio_monitor.host", default="127.0.0.1")
    port = BindDefault[int]("portfolio_monitor.port", default=8400)
    control_panel_port = BindDefault[int]("portfolio_monitor.control_panel_port", default=8401)
    auth_key = Bind[str]("portfolio_monitor.auth_key")

    # Dashboard credentials
    dashboard_username = Bind[str]("portfolio_monitor.dashboard.username")
    dashboard_password = Bind[str]("portfolio_monitor.dashboard.password")

    debug = BindDefault[bool]("portfolio_monitor.debug", default=False)
    dev_console = BindDefault[bool]("portfolio_monitor.dev_console", arg_key="dev", default=False)

    openclaw_host = BindDefault[str](
        "portfolio_monitor.openclaw.host", default="127.0.0.1"
    )
    openclaw_port = BindDefault[int]("portfolio_monitor.openclaw.port", default=18789)
    openclaw_auth_key = Bind[str]("portfolio_monitor.openclaw.auth_key")
    openclaw_agent_id = Bind[str]("portfolio_monitor.openclaw.agent_id")
    openclaw_session_key = BindDefault[str](
        "portfolio_monitor.openclaw.session_key", default="portfolio_alerts"
    )
    openclaw_gateway_token = Bind[str]("portfolio_monitor.openclaw.gateway_token")
    openclaw_gateway_password = Bind[str]("portfolio_monitor.openclaw.gateway_password")
    openclaw_gateway_device_identity_file = BindDefault[Path](
        "portfolio_monitor.openclaw.gateway_device_identity_file",
        default="config/device_identity.json",
        converter=Path,
    )

    # OpenClaw alert delivery
    openclaw_alert_enable_http = BindDefault[bool](
        "portfolio_monitor.openclaw.alert_enable_http", default=False
    )
    openclaw_alert_enable_ws = BindDefault[bool](
        "portfolio_monitor.openclaw.websocket.enabled", default=False
    )
    openclaw_alert_extra_prompt = BindDefault[str](
        "portfolio_monitor.openclaw.websocket.extra_prompt", default=""
    )
