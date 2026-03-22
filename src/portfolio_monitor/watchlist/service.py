import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from omegaconf import OmegaConf

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.watchlist.events import (
    WatchlistEntryAdded,
    WatchlistEntryAlertsUpdated,
    WatchlistEntryRemoved,
)
from portfolio_monitor.watchlist.models import Watchlist, WatchlistEntry

if TYPE_CHECKING:
    from portfolio_monitor.service.context import AuthContext

logger = logging.getLogger(__name__)

_UNSET = object()  # sentinel for "not provided" optional args


def _load_watchlists_by_owner(watchlist_path: Path) -> dict[str, list[Watchlist]]:
    """Load all watchlists from */<owner>/*.yaml, keyed by owner directory name."""
    by_owner: dict[str, list[Watchlist]] = {}
    if not watchlist_path.exists():
        return by_owner
    yaml_files = sorted(
        list(watchlist_path.glob("*/*.yaml")) + list(watchlist_path.glob("*/*.yml"))
    )
    for yaml_file in yaml_files:
        owner = yaml_file.parent.name
        try:
            with open(yaml_file) as f:
                data = OmegaConf.load(f)
            if "name" not in data:
                logger.warning("Watchlist file missing 'name': %s", yaml_file)
                continue
            raw = OmegaConf.to_container(data, resolve=True)
            wl = Watchlist.from_dict(raw, owner=owner)  # type: ignore[arg-type]
            by_owner.setdefault(owner, []).append(wl)
            logger.info("Loaded watchlist '%s' (owner=%s) from %s", wl.name, owner, yaml_file)
        except Exception:
            logger.exception("Error loading watchlist from %s", yaml_file)
    return by_owner


class WatchlistService:
    """Manages watchlists — CRUD with YAML persistence and live event publishing.

    Ownership mirrors portfolios: ``default/`` watchlists are global (all users),
    ``<username>/`` watchlists are visible only to that user and admins.
    """

    def __init__(self, bus: EventBus, watchlist_path: Path) -> None:
        self._bus: EventBus = bus
        self._watchlist_path: Path = watchlist_path
        self._by_owner: dict[str, list[Watchlist]] = _load_watchlists_by_owner(watchlist_path)
        self._tracked: set[AssetSymbol] = set()
        self._rebuild_tracked()
        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_tracked(self) -> None:
        self._tracked = {
            entry.symbol
            for wl in self.get_all_watchlists()
            for entry in wl.entries
        }

    def _watchlist_file(self, wl: Watchlist) -> Path:
        safe_name = wl.name.lower().replace(" ", "_")
        return self._watchlist_path / wl.owner / f"{safe_name}.yaml"

    def _save(self, wl: Watchlist) -> None:
        owner_dir = self._watchlist_path / wl.owner
        owner_dir.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(OmegaConf.create(wl.to_dict()), self._watchlist_file(wl))

    def _find_by_id(self, id: str) -> Watchlist | None:
        for wl in self.get_all_watchlists():
            if wl.id == id:
                return wl
        return None

    def _can_write(self, wl: Watchlist, auth: "AuthContext") -> bool:
        return (auth.is_admin and auth.username == "admin") or wl.owner == auth.username

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_all_watchlists(self) -> list[Watchlist]:
        return [wl for wls in self._by_owner.values() for wl in wls]

    def get_watchlists(self, auth: "AuthContext") -> list[Watchlist]:
        if auth.is_admin and auth.username == "admin":
            return self.get_all_watchlists()
        result = list(self._by_owner.get("default", []))
        result.extend(self._by_owner.get(auth.username, []))
        return result

    def get_watchlist(self, id: str, auth: "AuthContext") -> Watchlist | None:
        for wl in self.get_watchlists(auth):
            if wl.id == id:
                return wl
        return None

    # ------------------------------------------------------------------
    # Watchlist-level CRUD
    # ------------------------------------------------------------------

    async def create_watchlist(self, name: str, owner: str) -> Watchlist:
        wl = Watchlist(name=name, owner=owner)
        self._by_owner.setdefault(owner, []).append(wl)
        self._save(wl)
        logger.info("Created watchlist '%s' (owner=%s, id=%s)", name, owner, wl.id)
        return wl

    async def delete_watchlist(self, id: str, auth: "AuthContext") -> bool:
        wl = self._find_by_id(id)
        if wl is None or not self._can_write(wl, auth):
            return False
        owner_list = self._by_owner.get(wl.owner, [])
        try:
            owner_list.remove(wl)
        except ValueError:
            pass
        path = self._watchlist_file(wl)
        if path.exists():
            path.unlink()
        self._rebuild_tracked()
        return True

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    async def add_entry(
        self, id: str, entry: WatchlistEntry, auth: "AuthContext"
    ) -> Watchlist | None:
        wl = self._find_by_id(id)
        if wl is None or not self._can_write(wl, auth):
            return None
        # Replace existing entry with same ticker
        wl.entries = [e for e in wl.entries if e.symbol.ticker != entry.symbol.ticker]
        if entry.time_added is None:
            entry.time_added = datetime.now(timezone.utc)
        wl.entries.append(entry)
        self._save(wl)
        self._tracked.add(entry.symbol)
        await self._bus.publish(WatchlistEntryAdded(
            symbol=entry.symbol,
            alert_config=dict(entry.alerts),
            owner=wl.owner,
        ))
        return wl

    async def remove_entry(
        self, id: str, ticker: str, auth: "AuthContext"
    ) -> Watchlist | None:
        wl = self._find_by_id(id)
        if wl is None or not self._can_write(wl, auth):
            return None
        entry = wl.get_entry(ticker)
        if entry is None:
            return wl
        wl.entries = [e for e in wl.entries if e.symbol.ticker != ticker]
        self._save(wl)
        self._rebuild_tracked()
        await self._bus.publish(WatchlistEntryRemoved(symbol=entry.symbol, owner=wl.owner))
        return wl

    async def update_entry_alerts(
        self, id: str, ticker: str, alerts: dict[str, Any], auth: "AuthContext"
    ) -> Watchlist | None:
        wl = self._find_by_id(id)
        if wl is None or not self._can_write(wl, auth):
            return None
        entry = wl.get_entry(ticker)
        if entry is None:
            return None
        old_alerts = dict(entry.alerts)
        entry.alerts = alerts
        self._save(wl)
        await self._bus.publish(WatchlistEntryAlertsUpdated(
            symbol=entry.symbol,
            old_alert_config=old_alerts,
            new_alert_config=dict(alerts),
            owner=wl.owner,
        ))
        return wl

    async def update_entry_fields(
        self,
        id: str,
        ticker: str,
        *,
        notes: str | None = None,
        target_buy: float | None = _UNSET,   # type: ignore[assignment]
        target_sell: float | None = _UNSET,  # type: ignore[assignment]
        meta_patch: dict[str, Any] | None = None,
        auth: "AuthContext",
    ) -> Watchlist | None:
        wl = self._find_by_id(id)
        if wl is None or not self._can_write(wl, auth):
            return None
        entry = wl.get_entry(ticker)
        if entry is None:
            return None
        if notes is not None:
            entry.notes = notes
        if target_buy is not _UNSET:
            entry.target_buy = target_buy
        if target_sell is not _UNSET:
            entry.target_sell = target_sell
        if meta_patch is not None:
            entry.meta.update(meta_patch)
        self._save(wl)
        return wl

    # ------------------------------------------------------------------
    # Price update
    # ------------------------------------------------------------------

    async def _on_aggregate_updated(self, event: AggregateUpdated) -> None:
        if event.symbol not in self._tracked:
            return
        price = Currency(event.aggregate.close, Currency.DEFAULT_CURRENCY_TYPE)
        for wl in self.get_all_watchlists():
            for entry in wl.entries:
                if entry.symbol == event.symbol:
                    entry.current_price = price
