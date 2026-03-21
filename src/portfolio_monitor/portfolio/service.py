import logging
from pathlib import Path
from typing import TYPE_CHECKING

from omegaconf import OmegaConf

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.portfolio.events import PortfolioUpdated, PriceUpdated
from portfolio_monitor.portfolio.portfolio import Portfolio
from portfolio_monitor.service.types import AssetSymbol

if TYPE_CHECKING:
    from portfolio_monitor.service.context import AuthContext

logger = logging.getLogger(__name__)


def _load_portfolios_by_owner(portfolio_path: Path) -> dict[str, list[Portfolio]]:
    """Load all portfolios from */<owner>/*.yaml, keyed by owner directory name."""
    by_owner: dict[str, list[Portfolio]] = {}
    if not portfolio_path.exists():
        logger.warning("Portfolio path %s does not exist", portfolio_path)
        return by_owner
    yaml_files = sorted(
        list(portfolio_path.glob("*/*.yaml")) + list(portfolio_path.glob("*/*.yml"))
    )
    for yaml_file in yaml_files:
        owner = yaml_file.parent.name
        try:
            with open(yaml_file) as f:
                data = OmegaConf.load(f)
            if "name" not in data:
                logger.warning("YAML file does not contain a portfolio: %s", yaml_file)
                continue
            portfolio = Portfolio.from_dict(dict(data))
            by_owner.setdefault(owner, []).append(portfolio)
            logger.info(
                "Loaded portfolio '%s' (owner=%s) from %s",
                portfolio.name,
                owner,
                yaml_file,
            )
        except Exception:
            logger.exception("Error loading portfolio from %s", yaml_file)
    return by_owner


class PortfolioService:
    """Manages portfolio state and price updates.

    Loads portfolios from *portfolio_path*/<owner>/*.yaml on startup.
    Portfolios under ``default/`` are considered global (visible to all users).
    Portfolios under ``<username>/`` are visible only to that user (and admins).

    Subscribes to AggregateUpdated to push prices into portfolios.
    Publishes PriceUpdated and PortfolioUpdated events.
    """

    def __init__(self, bus: EventBus, portfolio_path: Path) -> None:
        self._bus: EventBus = bus
        self._portfolios_by_owner: dict[str, list[Portfolio]] = _load_portfolios_by_owner(
            portfolio_path
        )
        self._tracked_symbols: set[AssetSymbol] = set()

        for portfolio in self.get_all_portfolios():
            for asset in portfolio.assets():
                self._tracked_symbols.add(asset.symbol)

        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    def get_all_portfolios(self) -> list[Portfolio]:
        """Return every portfolio regardless of owner — for internal/admin use."""
        return [p for portfolios in self._portfolios_by_owner.values() for p in portfolios]

    def get_portfolios(self, auth: "AuthContext") -> list[Portfolio]:
        """Return portfolios visible to *auth*.

        Admins see all portfolios. Normal users see ``default/`` plus their own.
        """
        if auth.is_admin and auth.username == "admin":
            return self.get_all_portfolios()
        result = list(self._portfolios_by_owner.get("default", []))
        result.extend(self._portfolios_by_owner.get(auth.username, []))
        return result

    def get_portfolio(self, id: str, auth: "AuthContext") -> Portfolio | None:
        """Return the portfolio with the given id, scoped by *auth*."""
        for p in self.get_portfolios(auth):
            if p.id == id:
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

        for portfolio in self.get_all_portfolios():
            data_matched: bool = portfolio.update_prices(price_data)
            if data_matched:
                await self._bus.publish(PortfolioUpdated(portfolio_name=portfolio.name))

        await self._bus.publish(PriceUpdated(symbol=event.symbol, price=price))
