from dataclasses import dataclass

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.portfolio.service import PortfolioService


@dataclass
class PortfolioMonitorContext:
    """Runtime context passed to API handlers — holds config and live services."""

    config: PortfolioMonitorConfig
    portfolio_service: PortfolioService
