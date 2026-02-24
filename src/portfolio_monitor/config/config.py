from pathlib import Path
from typing import Any

from appconf import AppConfig, Bind, BindDefault


class PortfolioMonitorConfig(AppConfig):
    """Typed configuration for the Portfolio Monitor application."""

    portfolio_path = Bind[str]("portfolio_monitor.portfolio_path")
    aggregate_cache_path = BindDefault[Path](
        "portfolio_monitor.aggregate_cache_path",
        default="./config/aggregate_cache.db",
        converter=Path,
    )

    # Polygon.io settings
    polygon_api_key = Bind[str]("polygon.api_key")
    polygon_delay = BindDefault[int]("polygon.delay", default=15 * 60)

    # Monitor settings for securities
    monitors = BindDefault[dict[str, dict[str, Any]]](
        "portfolio_monitor.monitors", default={"default": {}}
    )
