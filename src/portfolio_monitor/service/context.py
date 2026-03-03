from dataclasses import dataclass

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.portfolio.service import PortfolioService


@dataclass
class PortfolioMonitorContext:
    """Runtime context passed to API handlers — holds config and live services."""

    config: PortfolioMonitorConfig
    portfolio_service: PortfolioService
    bus: EventBus
    data_provider: DataProvider
