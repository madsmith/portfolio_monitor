from pathlib import Path
from typing import Any

from appconf import AppConfig, Bind, BindDefault


class PortfolioMonitorConfig(AppConfig):
    """Typed configuration for the Portfolio Monitor application."""

    portfolio_path = Bind[Path](
        "portfolio_monitor.portfolio_path",
        converter=Path,
    )
    aggregate_cache_path = BindDefault[Path](
        "portfolio_monitor.aggregate_cache_path",
        default="./config/aggregate_cache.db",
        converter=Path,
    )

    # Polygon.io settings
    polygon_api_key = Bind[str]("polygon.api_key")
    polygon_delay = BindDefault[int]("polygon.delay", default=15 * 60)

    # Control interface settings
    host = BindDefault[str]("portfolio_monitor.host", default="127.0.0.1")
    port = BindDefault[int]("portfolio_monitor.port", default=8400)
    auth_key = Bind[str]("portfolio_monitor.auth_key")

    # Dashboard credentials
    dashboard_username = Bind[str]("portfolio_monitor.dashboard.username")
    dashboard_password = Bind[str]("portfolio_monitor.dashboard.password")

    # Monitor settings for securities
    monitors = BindDefault[dict[str, dict[str, Any]]](
        "portfolio_monitor.monitors", default={"default": {}}
    )

    debug = BindDefault[bool]("portfolio_monitor.debug", default=False)
