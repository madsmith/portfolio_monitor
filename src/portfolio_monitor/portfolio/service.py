import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml as pyyaml
from omegaconf import OmegaConf

from portfolio_monitor.core import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import AggregateUpdated
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

if TYPE_CHECKING:
    from portfolio_monitor.service.context import AuthContext

from .events import PortfolioUpdated, PriceUpdated
from .models import Asset, Lot, Portfolio

logger = logging.getLogger(__name__)


_ASSET_TYPE_ATTR: dict[str, str] = {"stock": "stocks", "currency": "currencies", "crypto": "crypto"}


def _load_portfolios_by_owner(portfolio_path: Path, path_registry: dict[str, Path] | None = None) -> dict[str, list[Portfolio]]:
    """Load all portfolios from */<owner>/*.yaml, keyed by owner directory name."""
    by_owner: dict[str, list[Portfolio]] = {}
    if not portfolio_path.exists():
        logger.warning("Portfolio path %s does not exist", portfolio_path)
        return by_owner
    yaml_files = sorted(
        list(portfolio_path.glob("*/*.yaml")) + list(portfolio_path.glob("*/*.yml"))
    )
    for yaml_file in yaml_files:
        folder_owner = yaml_file.parent.name
        try:
            with open(yaml_file) as f:
                data = OmegaConf.load(f)
            if "name" not in data:
                logger.warning("YAML file does not contain a portfolio: %s", yaml_file)
                continue
            owner = data.get("owner", folder_owner) or folder_owner
            had_id = bool(data.get("id"))
            portfolio = Portfolio.from_dict(dict(data), id_hash_seed=str(yaml_file), owner=owner)
            by_owner.setdefault(owner, []).append(portfolio)
            if path_registry is not None:
                path_registry[portfolio.id] = yaml_file
            if not had_id:
                with open(yaml_file, "w") as wf:
                    pyyaml.dump(portfolio.to_dict(), wf, default_flow_style=False, allow_unicode=True, sort_keys=False)
                logger.info("Persisted id '%s' to %s", portfolio.id, yaml_file)
            logger.info(
                "Loaded portfolio '%s' (owner=%s, id=%s) from %s",
                portfolio.name,
                owner,
                portfolio.id,
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
        self._portfolio_paths: dict[str, Path] = {}
        self._portfolios_by_owner: dict[str, list[Portfolio]] = _load_portfolios_by_owner(
            portfolio_path, self._portfolio_paths
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

    #######################################################
    # Event Bus Callbacks
    #######################################################

    #######################################################
    # Mutations
    #######################################################

    def _can_write(self, portfolio: Portfolio, auth: "AuthContext") -> bool:
        return auth.is_admin or portfolio.can("write", auth.username)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        path = self._portfolio_paths.get(portfolio.id)
        if path is None:
            raise ValueError(f"No file path tracked for portfolio {portfolio.id}")
        with open(path, "w") as f:
            pyyaml.dump(portfolio.to_dict(), f, default_flow_style=False, allow_unicode=True, sort_keys=False)

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
