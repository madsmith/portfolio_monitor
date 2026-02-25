import logging

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.portfolio.events import PortfolioUpdated, PriceUpdated
from portfolio_monitor.portfolio.portfolio import Portfolio
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


class PortfolioService:
    """Manages portfolio state and price updates.

    Subscribes to AggregateUpdated to push prices into portfolios.
    Publishes PriceUpdated and PortfolioUpdated events.
    """

    def __init__(self, bus: EventBus, portfolios: list[Portfolio]) -> None:
        self._bus: EventBus = bus
        self._portfolios: list[Portfolio] = portfolios
        self._tracked_symbols: set[AssetSymbol] = set()

        for portfolio in portfolios:
            for asset in portfolio.assets():
                self._tracked_symbols.add(asset.symbol)

        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    def get_portfolios(self) -> list[Portfolio]:
        return self._portfolios

    def get_portfolio(self, name: str) -> Portfolio | None:
        for p in self._portfolios:
            if p.name == name:
                return p
        return None

    #######################################################
    # Event Bus Callbacks
    #######################################################

    async def _on_aggregate_updated(self, event: AggregateUpdated) -> None:
        if event.symbol not in self._tracked_symbols:
            return

        price: Currency = Currency(
            event.aggregate.close, Currency.DEFAULT_CURRENCY_TYPE
        )
        price_data: dict[AssetSymbol, Currency] = {event.symbol: price}

        for portfolio in self._portfolios:
            data_matched: bool = portfolio.update_prices(price_data)
            if data_matched:
                await self._bus.publish(PortfolioUpdated(portfolio_name=portfolio.name))

        await self._bus.publish(PriceUpdated(symbol=event.symbol, price=price))
