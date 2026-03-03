import logging

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.provider import PolygonDataProvider
from portfolio_monitor.portfolio.portfolio import Portfolio
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


class SeedPriceProvider:
    """Fetches previous-close prices from Polygon to seed synthetic simulation.

    Call load() once (async) before passing to SyntheticDataSource.
    Any symbol whose fetch fails is omitted; SyntheticDataSource will
    fall back to its own default (100.0) for those tickers.
    """

    def __init__(
        self,
        portfolios: list[Portfolio],
        data_provider: PolygonDataProvider,
    ) -> None:
        self._portfolios: list[Portfolio] = portfolios
        self._data_provider: PolygonDataProvider = data_provider
        self._prices: dict[str, float] = {}
        self._aggregates: dict[str, Aggregate] = {}

    async def load(self) -> None:
        """Fetch previous close for every unique asset symbol across all portfolios."""
        symbols: set[AssetSymbol] = {
            asset.symbol
            for portfolio in self._portfolios
            for asset in portfolio.assets()
        }
        logger.info("Fetching seed prices for %d symbols from Polygon...", len(symbols))
        for symbol in symbols:
            try:
                agg = await self._data_provider.get_previous_close(symbol)
                if agg is not None:
                    self._prices[symbol.ticker] = agg.close
                    self._aggregates[symbol.ticker] = agg
                    logger.debug("Seed price %s = %.4f", symbol.ticker, agg.close)
                else:
                    logger.warning(
                        "No previous close returned for %s; will use default seed price",
                        symbol.ticker,
                    )
            except Exception:
                logger.warning(
                    "Failed to fetch seed price for %s; will use default seed price",
                    symbol.ticker,
                    exc_info=True,
                )
        logger.info(
            "Seed prices loaded: %d/%d symbols fetched successfully",
            len(self._prices),
            len(symbols),
        )

    def get_prices(self) -> dict[str, float]:
        """Return the loaded seed prices. Ensure load() has been awaited first."""
        return dict(self._prices)

    def get_aggregates(self) -> dict[str, Aggregate]:
        """Return the loaded seed aggregates. Ensure load() has been awaited first."""
        return dict(self._aggregates)
