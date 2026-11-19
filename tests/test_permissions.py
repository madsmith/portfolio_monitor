"""Tests for the core permission system and its integration with Watchlist/Portfolio."""

import pytest
import pytest_asyncio

from portfolio_monitor.core.permissions import PermissionMap, UserPermission
from portfolio_monitor.portfolio.models import Portfolio
from portfolio_monitor.watchlist.models import Watchlist


# ---------------------------------------------------------------------------
# PermissionMap
# ---------------------------------------------------------------------------


class TestPermissionMap:
    def test_from_yaml_dict(self):
        pm = PermissionMap.from_yaml({"martin": {"read": True, "write": True}})
        entry = pm.get("martin")
        assert entry is not None
        assert entry.read is True
        assert entry.write is True

    def test_from_yaml_dict_partial_flags(self):
        pm = PermissionMap.from_yaml({"alice": {"read": True, "write": False}})
        entry = pm.get("alice")
        assert entry is not None
        assert entry.read is True
        assert entry.write is False

    def test_from_yaml_dict_missing_flags_default_false(self):
        pm = PermissionMap.from_yaml({"bob": {}})
        entry = pm.get("bob")
        assert entry is not None
        assert entry.read is False
        assert entry.write is False

    def test_from_yaml_list_of_dicts(self):
        pm = PermissionMap.from_yaml([
            {"martin": {"read": True, "write": True}},
            {"alice": {"read": True, "write": False}},
        ])
        assert pm.get("martin") == UserPermission(read=True, write=True)
        assert pm.get("alice") == UserPermission(read=True, write=False)

    def test_from_yaml_invalid_returns_empty(self):
        pm = PermissionMap.from_yaml(None)
        assert pm.get("anyone") is None

        pm2 = PermissionMap.from_yaml("not-a-dict")
        assert pm2.get("anyone") is None

    def test_get_returns_none_for_unknown_user(self):
        pm = PermissionMap.from_yaml({"martin": {"read": True, "write": True}})
        assert pm.get("nobody") is None

    def test_to_dict_round_trip(self):
        original = {"martin": {"read": True, "write": True}, "alice": {"read": True, "write": False}}
        pm = PermissionMap.from_yaml(original)
        assert pm.to_dict() == original

    def test_to_dict_empty(self):
        pm = PermissionMap()
        assert pm.to_dict() == {}


# ---------------------------------------------------------------------------
# PermissionsHost.can() — implicit rules via Watchlist
# ---------------------------------------------------------------------------


class TestImplicitPermissions:
    def test_default_owner_not_readable_by_others(self):
        wl = Watchlist(name="Unowned", owner="default")
        assert wl.can("read", "alice") is False
        assert wl.can("read", "bob") is False
        assert wl.can("read", "admin") is False  # admin bypass lives in the service layer

    def test_default_owner_not_writable(self):
        wl = Watchlist(name="Unowned", owner="default")
        assert wl.can("write", "alice") is False

    def test_default_string_is_not_an_owner(self):
        # "default" is a placeholder, so a user literally named "default" gets no access.
        wl = Watchlist(name="Unowned", owner="default")
        assert wl.can("read", "default") is False
        assert wl.can("write", "default") is False

    def test_named_owner_can_read_and_write(self):
        wl = Watchlist(name="Private", owner="martin")
        assert wl.can("read", "martin") is True
        assert wl.can("write", "martin") is True

    def test_named_owner_denies_other_users(self):
        wl = Watchlist(name="Private", owner="martin")
        assert wl.can("read", "alice") is False
        assert wl.can("write", "alice") is False

    def test_named_owner_denies_default_string(self):
        wl = Watchlist(name="Private", owner="martin")
        assert wl.can("read", "default") is False


# ---------------------------------------------------------------------------
# PermissionsHost.can() — explicit permissions block
# ---------------------------------------------------------------------------


class TestExplicitPermissions:
    @pytest.fixture
    def shared_watchlist(self) -> Watchlist:
        pm = PermissionMap.from_yaml({
            "martin": {"read": True, "write": True},
            "alice": {"read": True, "write": False},
        })
        return Watchlist(name="Shared", owner="martin", permissions=pm)

    def test_listed_user_read(self, shared_watchlist: Watchlist):
        assert shared_watchlist.can("read", "martin") is True
        assert shared_watchlist.can("read", "alice") is True

    def test_listed_user_write(self, shared_watchlist: Watchlist):
        assert shared_watchlist.can("write", "martin") is True
        assert shared_watchlist.can("write", "alice") is False

    def test_unlisted_user_denied(self, shared_watchlist: Watchlist):
        assert shared_watchlist.can("read", "bob") is False
        assert shared_watchlist.can("write", "bob") is False

    def test_owner_always_has_full_access_even_with_explicit_block(self, shared_watchlist: Watchlist):
        # martin is the owner — full access regardless of what the permissions block says
        assert shared_watchlist.can("read", "martin") is True
        assert shared_watchlist.can("write", "martin") is True

    def test_owner_has_access_even_when_not_listed_in_permissions(self):
        # Owner is not mentioned in the permissions block at all
        pm = PermissionMap.from_yaml({"alice": {"read": True, "write": False}})
        wl = Watchlist(name="NotListed", owner="martin", permissions=pm)
        assert wl.can("read", "martin") is True
        assert wl.can("write", "martin") is True

    def test_explicit_grant_on_default_owner(self):
        # Items with no real owner are only reachable via an explicit grant.
        pm = PermissionMap.from_yaml({"martin": {"read": True, "write": False}})
        wl = Watchlist(name="Restricted Default", owner="default", permissions=pm)
        assert wl.can("read", "martin") is True
        assert wl.can("read", "alice") is False  # unlisted — denied despite "default" owner


# ---------------------------------------------------------------------------
# Watchlist — from_dict / to_dict with permissions
# ---------------------------------------------------------------------------


class TestWatchlistPermissionParsing:
    def test_from_dict_no_permissions_field(self):
        wl = Watchlist.from_dict({"name": "Plain"}, owner="martin")
        assert wl.permissions is None
        assert wl.can("read", "martin") is True
        assert wl.can("read", "alice") is False

    def test_from_dict_with_permissions_dict(self):
        data = {
            "name": "Shared",
            "permissions": {
                "alice": {"read": True, "write": False},
            },
        }
        wl = Watchlist.from_dict(data, owner="martin")
        assert wl.permissions is not None
        assert wl.can("read", "alice") is True
        assert wl.can("write", "alice") is False
        assert wl.can("read", "martin") is True   # owner always has access
        assert wl.can("write", "martin") is True  # even if not listed in explicit block

    def test_from_dict_with_permissions_list(self):
        data = {
            "name": "Shared",
            "permissions": [{"alice": {"read": True, "write": True}}],
        }
        wl = Watchlist.from_dict(data, owner="martin")
        assert wl.can("read", "alice") is True
        assert wl.can("write", "alice") is True

    def test_to_dict_omits_permissions_when_none(self):
        wl = Watchlist.from_dict({"name": "Plain"}, owner="martin")
        d = wl.to_dict()
        assert "permissions" not in d

    def test_to_dict_includes_permissions_when_set(self):
        data = {
            "name": "Shared",
            "id": "abc123",
            "permissions": {"alice": {"read": True, "write": False}},
        }
        wl = Watchlist.from_dict(data, owner="martin")
        d = wl.to_dict()
        assert d["permissions"] == {"alice": {"read": True, "write": False}}

    def test_to_dict_round_trip(self):
        data = {
            "name": "Shared",
            "id": "abc123",
            "entries": [],
            "permissions": {
                "alice": {"read": True, "write": False},
                "martin": {"read": True, "write": True},
            },
        }
        wl = Watchlist.from_dict(data, owner="martin")
        assert wl.to_dict() == data


# ---------------------------------------------------------------------------
# Portfolio — owner field and permission parsing
# ---------------------------------------------------------------------------


class TestPortfolioPermissions:
    def test_default_owner_is_default(self):
        p = Portfolio(name="Test")
        assert p.owner == "default"

    def test_from_dict_sets_owner(self):
        p = Portfolio.from_dict({"name": "My Portfolio"}, owner="martin")
        assert p.owner == "martin"
        assert p.can("read", "martin") is True
        assert p.can("read", "alice") is False

    def test_from_dict_default_owner_private(self):
        p = Portfolio.from_dict({"name": "Unowned Portfolio"}, owner="default")
        assert p.can("read", "anyone") is False
        assert p.can("write", "anyone") is False

    def test_from_dict_with_permissions(self):
        data = {
            "name": "Shared Portfolio",
            "permissions": {
                "alice": {"read": True, "write": False},
                "martin": {"read": True, "write": True},
            },
        }
        p = Portfolio.from_dict(data, owner="martin")
        assert p.can("read", "alice") is True
        assert p.can("write", "alice") is False
        assert p.can("read", "martin") is True
        assert p.can("write", "martin") is True
        assert p.can("read", "bob") is False

    def test_from_dict_no_permissions_falls_back_to_implicit(self):
        p = Portfolio.from_dict({"name": "Mine"}, owner="martin")
        assert p.permissions is None
        assert p.can("read", "martin") is True
        assert p.can("read", "alice") is False


# ---------------------------------------------------------------------------
# Service-level filtering
# ---------------------------------------------------------------------------
#
# Services are backed by a real temporary SQLite database (YAML loading is gone).
# Fixture layout, per service:
#   default-owned item   — no real owner; reachable only by admins
#   martin's private item — owner-only
#   martin's shared item  — alice read-only, granted via update_permissions


def _auth(username: str, role: str = "normal"):
    from portfolio_monitor.service.context import AuthContext
    return AuthContext(username=username, role=role)


ADMIN = ("admin", "admin")


@pytest.fixture
def db(tmp_path):
    from portfolio_monitor.data.database import AppDatabase
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()
    yield database
    database.close()


class TestWatchlistServiceFiltering:
    @pytest_asyncio.fixture
    async def service(self, db):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.watchlist.service import WatchlistService
        svc = WatchlistService(EventBus(), db)
        await svc.create_watchlist("Global", "default")
        await svc.create_watchlist("Private", "martin")
        shared = await svc.create_watchlist("Shared", "martin")
        svc.update_permissions(shared.id, {"alice": {"read": True, "write": False}}, _auth("martin"))
        return svc

    def _named(self, service, name):
        return next(w for w in service.get_all_watchlists() if w.name == name)

    @pytest.mark.asyncio
    async def test_admin_sees_all(self, service):
        wls = service.get_watchlists(_auth(*ADMIN))
        assert {wl.name for wl in wls} == {"Global", "Private", "Shared"}

    @pytest.mark.asyncio
    async def test_default_owned_hidden_from_normal_users(self, service):
        for username in ("martin", "alice", "bob"):
            names = {wl.name for wl in service.get_watchlists(_auth(username))}
            assert "Global" not in names, f"{username} should not see a default-owned watchlist"

    @pytest.mark.asyncio
    async def test_owner_sees_own_watchlists(self, service):
        names = {wl.name for wl in service.get_watchlists(_auth("martin"))}
        assert {"Private", "Shared"} <= names

    @pytest.mark.asyncio
    async def test_unrelated_user_cannot_see_private(self, service):
        names = {wl.name for wl in service.get_watchlists(_auth("alice"))}
        assert "Private" not in names

    @pytest.mark.asyncio
    async def test_explicitly_shared_read_visible_to_grantee(self, service):
        names = {wl.name for wl in service.get_watchlists(_auth("alice"))}
        assert "Shared" in names

    @pytest.mark.asyncio
    async def test_unlisted_user_cannot_see_explicitly_shared(self, service):
        names = {wl.name for wl in service.get_watchlists(_auth("bob"))}
        assert "Shared" not in names

    @pytest.mark.asyncio
    async def test_can_write_owner(self, service):
        assert service._can_write(self._named(service, "Private"), _auth("martin")) is True

    @pytest.mark.asyncio
    async def test_can_write_non_owner_denied(self, service):
        assert service._can_write(self._named(service, "Private"), _auth("alice")) is False

    @pytest.mark.asyncio
    async def test_can_write_owner_of_shared(self, service):
        assert service._can_write(self._named(service, "Shared"), _auth("martin")) is True

    @pytest.mark.asyncio
    async def test_can_write_read_only_grantee_denied(self, service):
        assert service._can_write(self._named(service, "Shared"), _auth("alice")) is False

    @pytest.mark.asyncio
    async def test_admin_can_write_anything(self, service):
        for wl in service.get_all_watchlists():
            assert service._can_write(wl, _auth(*ADMIN)) is True

    @pytest.mark.asyncio
    async def test_visibility_survives_reload(self, service, db):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.watchlist.service import WatchlistService
        reloaded = WatchlistService(EventBus(), db)
        assert {wl.name for wl in reloaded.get_watchlists(_auth("alice"))} == {"Shared"}


class TestPortfolioServiceFiltering:
    @pytest.fixture
    def service(self, db):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.portfolio.service import PortfolioService
        svc = PortfolioService(EventBus(), db)
        svc.create_portfolio("Global Portfolio", _auth("default"))
        svc.create_portfolio("Martin Private", _auth("martin"))
        shared = svc.create_portfolio("Martin Shared", _auth("martin"))
        svc.update_permissions(shared.id, {"alice": {"read": True, "write": False}}, _auth("martin"))
        return svc

    def test_admin_sees_all(self, service):
        portfolios = service.get_portfolios(_auth(*ADMIN))
        assert {p.name for p in portfolios} == {"Global Portfolio", "Martin Private", "Martin Shared"}

    def test_default_owned_hidden_from_normal_users(self, service):
        for username in ("martin", "alice", "bob"):
            names = {p.name for p in service.get_portfolios(_auth(username))}
            assert "Global Portfolio" not in names

    def test_owner_sees_own_portfolios(self, service):
        names = {p.name for p in service.get_portfolios(_auth("martin"))}
        assert {"Martin Private", "Martin Shared"} <= names

    def test_other_user_cannot_see_private(self, service):
        names = {p.name for p in service.get_portfolios(_auth("alice"))}
        assert "Martin Private" not in names

    def test_explicitly_shared_visible_to_grantee(self, service):
        names = {p.name for p in service.get_portfolios(_auth("alice"))}
        assert "Martin Shared" in names

    def test_unlisted_user_denied_explicit_permissions(self, service):
        names = {p.name for p in service.get_portfolios(_auth("bob"))}
        assert "Martin Shared" not in names

    def test_visibility_survives_reload(self, service, db):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.portfolio.service import PortfolioService
        reloaded = PortfolioService(EventBus(), db)
        assert {p.name for p in reloaded.get_portfolios(_auth("alice"))} == {"Martin Shared"}
