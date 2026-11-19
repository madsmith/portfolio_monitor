"""WatchlistService rename and ID allocation, against a real temporary database."""

import pytest

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.service.context import AuthContext
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.watchlist.models import WatchlistEntry
from portfolio_monitor.watchlist.service import WatchlistService

MARTIN = AuthContext(username="martin", role="user")
ALICE = AuthContext(username="alice", role="user")
ADMIN = AuthContext(username="admin", role="admin")


@pytest.fixture
def db(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def service(db):
    return WatchlistService(EventBus(), db)


async def _populated(service: WatchlistService, name: str = "AI Datacenter"):
    wl = await service.create_watchlist(name, "martin")
    await service.add_entry(wl.id, WatchlistEntry(symbol=AssetSymbol("NVDA", AssetTypes.Stock)), MARTIN)
    service.update_permissions(wl.id, {"alice": {"read": True, "write": False}}, MARTIN)
    return wl


@pytest.mark.asyncio
async def test_rename_keeps_id_entries_and_permissions(service, db):
    wl = await _populated(service)
    renamed = service.rename_watchlist(wl.id, "  AI Infra  ", MARTIN)
    assert renamed is not None and renamed.id == wl.id and renamed.name == "AI Infra"

    # Reload from the database to make sure it persisted intact.
    reloaded = WatchlistService(EventBus(), db).get_watchlist(wl.id, MARTIN)
    assert reloaded is not None
    assert reloaded.name == "AI Infra"
    assert [e.symbol.ticker for e in reloaded.entries] == ["NVDA"]
    assert reloaded.can("read", "alice") is True


@pytest.mark.asyncio
async def test_rename_denied_for_non_owner(service):
    wl = await _populated(service)
    # alice has read access but is not the owner.
    assert service.rename_watchlist(wl.id, "Hijacked", ALICE) is None
    assert service.get_watchlist(wl.id, MARTIN).name == "AI Datacenter"


@pytest.mark.asyncio
async def test_rename_allowed_for_admin(service):
    wl = await _populated(service)
    assert service.rename_watchlist(wl.id, "By Admin", ADMIN).name == "By Admin"


@pytest.mark.asyncio
async def test_rename_rejects_empty_name(service):
    wl = await _populated(service)
    with pytest.raises(ValueError):
        service.rename_watchlist(wl.id, "   ", MARTIN)


@pytest.mark.asyncio
async def test_rename_unknown_id(service):
    assert service.rename_watchlist("does-not-exist", "X", MARTIN) is None


@pytest.mark.asyncio
async def test_reusing_old_name_after_rename_does_not_clobber(service, db):
    """Regression: name-derived IDs let a new list overwrite (and cascade-delete) a renamed one."""
    wl = await _populated(service)
    service.rename_watchlist(wl.id, "AI Infra", MARTIN)

    fresh = await service.create_watchlist("AI Datacenter", "martin")
    assert fresh.id != wl.id

    reloaded = WatchlistService(EventBus(), db).get_watchlist(wl.id, MARTIN)
    assert reloaded is not None and reloaded.name == "AI Infra"
    assert [e.symbol.ticker for e in reloaded.entries] == ["NVDA"]
    assert reloaded.can("read", "alice") is True


@pytest.mark.asyncio
async def test_duplicate_names_get_distinct_ids(service):
    a = await service.create_watchlist("Same", "martin")
    b = await service.create_watchlist("Same", "martin")
    assert a.id != b.id
    assert len(a.id) == 16 and len(b.id) == 16


BOB = AuthContext(username="bob", role="user")


@pytest.mark.asyncio
async def test_write_grantee_can_rename_but_not_share(service):
    wl = await service.create_watchlist("Agent List", "taylor")
    service.update_permissions(wl.id, {"bob": {"read": True, "write": True}},
                               AuthContext(username="taylor", role="user"))
    assert service.can_rename(wl, BOB) is True
    assert service.can_share(wl, BOB) is False
    assert service.rename_watchlist(wl.id, "Renamed by Bob", BOB).name == "Renamed by Bob"
    assert service.update_permissions(wl.id, {"bob": {"read": True, "write": True}, "eve": {"read": True}}, BOB) is None


@pytest.mark.asyncio
async def test_read_grantee_can_neither_rename_nor_share(service):
    wl = await _populated(service)  # alice: read-only
    assert service.can_rename(wl, ALICE) is False
    assert service.can_share(wl, ALICE) is False


@pytest.mark.asyncio
async def test_admin_can_rename_and_share_any(service):
    wl = await service.create_watchlist("Someone Else's", "taylor")
    assert service.can_rename(wl, ADMIN) is True
    assert service.can_share(wl, ADMIN) is True
