import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from portfolio_monitor.core import Currency
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.core.permissions import PermissionMap
from portfolio_monitor.data import AggregateUpdated
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.watchlist.events import (
    WatchlistEntryAdded,
    WatchlistEntryRemoved,
)
from portfolio_monitor.watchlist.models import Watchlist, WatchlistEntry

if TYPE_CHECKING:
    from portfolio_monitor.service.context import AuthContext

logger = logging.getLogger(__name__)

_UNSET = object()  # sentinel for "not provided" optional args


class WatchlistService:
    """Manages watchlists — CRUD with SQLite persistence and live event publishing.

    Ownership mirrors portfolios: a watchlist is visible only to its owner and
    admins, plus any users granted access via its ``permissions`` block.
    """

    def __init__(self, bus: EventBus, db: AppDatabase) -> None:
        self._bus: EventBus = bus
        self._watchlists_module = db.watchlists
        self._by_owner: dict[str, list[Watchlist]] = {}
        self._tracked: set[AssetSymbol] = set()

        for wl in db.watchlists.get_all():
            self._by_owner.setdefault(wl.owner, []).append(wl)
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

    def _save(self, wl: Watchlist) -> None:
        self._watchlists_module.upsert(wl)

    def _find_by_id(self, id: str) -> Watchlist | None:
        for wl in self.get_all_watchlists():
            if wl.id == id:
                return wl
        return None

    def _can_write(self, wl: Watchlist, auth: "AuthContext") -> bool:
        return (auth.is_admin and auth.username == "admin") or wl.can("write", auth.username)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_all_watchlists(self) -> list[Watchlist]:
        return [wl for wls in self._by_owner.values() for wl in wls]

    def get_watchlists(self, auth: "AuthContext") -> list[Watchlist]:
        if auth.is_admin and auth.username == "admin":
            return self.get_all_watchlists()
        return [wl for wl in self.get_all_watchlists() if wl.can("read", auth.username)]

    def get_watchlist(self, id: str, auth: "AuthContext") -> Watchlist | None:
        for wl in self.get_watchlists(auth):
            if wl.id == id:
                return wl
        return None

    # ------------------------------------------------------------------
    # Watchlist-level CRUD
    # ------------------------------------------------------------------

    def _new_id(self) -> str:
        # Random rather than derived from the name: name-derived IDs collide after a
        # rename (or with duplicate names), and the INSERT OR REPLACE upsert would then
        # cascade-delete the existing watchlist's entries and permissions.
        while True:
            candidate = secrets.token_hex(8)
            if self._find_by_id(candidate) is None:
                return candidate

    async def create_watchlist(self, name: str, owner: str) -> Watchlist:
        wl = Watchlist(name=name, owner=owner, id=self._new_id())
        self._by_owner.setdefault(owner, []).append(wl)
        self._watchlists_module.upsert(wl)
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
        self._watchlists_module.delete(id)
        self._rebuild_tracked()
        return True

    def can_rename(self, wl: Watchlist, auth: "AuthContext") -> bool:
        """Owner, admins, and users granted write access may rename."""
        return auth.is_admin or wl.can("write", auth.username)

    def can_share(self, wl: Watchlist, auth: "AuthContext") -> bool:
        """Only the owner and admins may change who a watchlist is shared with."""
        return auth.is_admin or wl.owner == auth.username

    def rename_watchlist(self, id: str, name: str, auth: "AuthContext") -> Watchlist | None:
        """Rename a watchlist (see ``can_rename``); the ID is unchanged.

        Returns None if not found or not permitted. Raises ValueError for an empty name.
        """
        name = name.strip()
        if not name:
            raise ValueError("name is required")
        wl = self._find_by_id(id)
        if wl is None or not self.can_rename(wl, auth):
            return None
        old = wl.name
        wl.name = name
        self._save(wl)
        logger.info("Renamed watchlist %s '%s' -> '%s'", wl.id, old, name)
        return wl

    def update_permissions(
        self,
        id: str,
        permissions: dict[str, dict[str, bool]],
        auth: "AuthContext",
    ) -> Watchlist | None:
        wl = self._find_by_id(id)
        if wl is None or not self.can_share(wl, auth):
            return None
        wl.permissions = PermissionMap.from_yaml(permissions) if permissions else None
        self._save(wl)
        return wl

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
