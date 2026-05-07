import logging
from typing import TYPE_CHECKING, Any

from portfolio_monitor.core import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.core.permissions import PermissionMap
from portfolio_monitor.data import AggregateUpdated
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

if TYPE_CHECKING:
    from portfolio_monitor.service.context import AuthContext

from .events import PortfolioUpdated, PriceUpdated
from .models import Asset, Lot, Portfolio

logger = logging.getLogger(__name__)


_ASSET_TYPE_ATTR: dict[str, str] = {"stock": "stocks", "currency": "currencies", "crypto": "crypto"}


class PortfolioService:
    """Manages portfolio state and price updates, backed by PortfoliosModule (SQLite).

    Portfolios are loaded from the database on startup into an in-memory cache.
    Mutations update both the cache and the database.

    Subscribes to AggregateUpdated to push prices into portfolios.
    Publishes PriceUpdated and PortfolioUpdated events.
    """

    def __init__(self, bus: EventBus, db: AppDatabase) -> None:
        self._bus: EventBus = bus
        self._portfolios_module = db.portfolios
        self._portfolios_by_owner: dict[str, list[Portfolio]] = {}
        self._tracked_symbols: set[AssetSymbol] = set()

        for portfolio in db.portfolios.get_all():
            self._portfolios_by_owner.setdefault(portfolio.owner, []).append(portfolio)
            for asset in portfolio.assets():
                self._tracked_symbols.add(asset.symbol)

        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    def get_all_portfolios(self) -> list[Portfolio]:
        """Return every portfolio regardless of owner — for internal/admin use."""
        return [p for portfolios in self._portfolios_by_owner.values() for p in portfolios]

    def get_portfolios(self, auth: "AuthContext") -> list[Portfolio]:
        """Return portfolios visible to *auth*.

        Admins see all portfolios. Normal users see portfolios they can read
        (implicit: ``default/`` owner is world-readable, ``<name>/`` owner is
        owner-only; explicit ``permissions:`` blocks override both).
        """
        if auth.is_admin and auth.username == "admin":
            return self.get_all_portfolios()
        return [p for p in self.get_all_portfolios() if p.can("read", auth.username)]

    def get_portfolio(self, id: str, auth: "AuthContext") -> Portfolio | None:
        """Return the portfolio with the given id, scoped by *auth*."""
        for p in self.get_portfolios(auth):
            if p.id == id:
                return p
        return None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def _can_write(self, portfolio: Portfolio, auth: "AuthContext") -> bool:
        return auth.is_admin or portfolio.can("write", auth.username)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        self._portfolios_module.upsert(portfolio)

    def _asset_list(self, portfolio: Portfolio, asset_type: str) -> list[Asset] | None:
        attr = _ASSET_TYPE_ATTR.get(asset_type)
        return getattr(portfolio, attr) if attr else None

    def add_lot(self, portfolio_id: str, asset_type: str, ticker: str, lot_data: dict[str, Any], auth: "AuthContext") -> tuple[Portfolio, Asset] | None:
        portfolio = self.get_portfolio(portfolio_id, auth)
        if portfolio is None or not self._can_write(portfolio, auth):
            return None
        asset_list = self._asset_list(portfolio, asset_type)
        if asset_list is None:
            return None
        asset = next((a for a in asset_list if a.symbol.ticker == ticker), None)
        if asset is None:
            symbol = AssetSymbol(ticker, AssetTypes(asset_type))
            asset = Asset(symbol=symbol, lots=[], asset_type=asset_type)
            asset_list.append(asset)
            self._tracked_symbols.add(symbol)
        asset.lots.append(Lot.from_dict(lot_data))
        self._save_portfolio(portfolio)
        return portfolio, asset

    def update_lot(self, portfolio_id: str, asset_type: str, ticker: str, lot_idx: int, lot_data: dict[str, Any], auth: "AuthContext") -> tuple[Portfolio, Asset] | None:
        portfolio = self.get_portfolio(portfolio_id, auth)
        if portfolio is None or not self._can_write(portfolio, auth):
            return None
        asset_list = self._asset_list(portfolio, asset_type)
        if asset_list is None:
            return None
        asset = next((a for a in asset_list if a.symbol.ticker == ticker), None)
        if asset is None or lot_idx < 0 or lot_idx >= len(asset.lots):
            return None
        asset.lots[lot_idx] = Lot.from_dict(lot_data)
        self._save_portfolio(portfolio)
        return portfolio, asset

    def delete_lot(self, portfolio_id: str, asset_type: str, ticker: str, lot_idx: int, auth: "AuthContext") -> Portfolio | None:
        portfolio = self.get_portfolio(portfolio_id, auth)
        if portfolio is None or not self._can_write(portfolio, auth):
            return None
        asset_list = self._asset_list(portfolio, asset_type)
        if asset_list is None:
            return None
        asset = next((a for a in asset_list if a.symbol.ticker == ticker), None)
        if asset is None or lot_idx < 0 or lot_idx >= len(asset.lots):
            return None
        asset.lots.pop(lot_idx)
        if not asset.lots:
            asset_list.remove(asset)
            self._tracked_symbols.discard(asset.symbol)
        self._save_portfolio(portfolio)
        return portfolio

    def update_permissions(
        self,
        portfolio_id: str,
        permissions: dict[str, dict[str, bool]],
        auth: "AuthContext",
    ) -> Portfolio | None:
        portfolio = self.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return None
        if not auth.is_admin and portfolio.owner != auth.username:
            return None
        portfolio.permissions = PermissionMap.from_yaml(permissions) if permissions else None
        self._save_portfolio(portfolio)
        return portfolio

    def delete_asset(self, portfolio_id: str, asset_type: str, ticker: str, auth: "AuthContext") -> Portfolio | None:
        portfolio = self.get_portfolio(portfolio_id, auth)
        if portfolio is None or not self._can_write(portfolio, auth):
            return None
        asset_list = self._asset_list(portfolio, asset_type)
        if asset_list is None:
            return None
        asset = next((a for a in asset_list if a.symbol.ticker == ticker), None)
        if asset is None:
            return None
        asset_list.remove(asset)
        self._tracked_symbols.discard(asset.symbol)
        self._save_portfolio(portfolio)
        return portfolio

    # ------------------------------------------------------------------
    # Event bus callbacks
    # ------------------------------------------------------------------

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
