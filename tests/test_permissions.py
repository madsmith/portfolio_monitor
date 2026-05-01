"""Tests for the core permission system and its integration with Watchlist/Portfolio."""

import pytest

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
    def test_default_owner_world_readable(self):
        wl = Watchlist(name="Global", owner="default")
        assert wl.can("read", "alice") is True
        assert wl.can("read", "bob") is True
        assert wl.can("read", "admin") is True

    def test_default_owner_not_writable(self):
        wl = Watchlist(name="Global", owner="default")
        assert wl.can("write", "alice") is False
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

    def test_explicit_overrides_default_owner_rule(self):
        # "default" owner would normally be world-readable, but an explicit
        # permissions block takes full control.
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

    def test_from_dict_default_owner_world_readable(self):
        p = Portfolio.from_dict({"name": "Global Portfolio"}, owner="default")
        assert p.can("read", "anyone") is True
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


class TestWatchlistServiceFiltering:
    @pytest.fixture
    def watchlist_dir(self, tmp_path):
        """Populate a temp watchlist directory with owner-scoped YAML files."""
        # default/ — world-readable
        (tmp_path / "default").mkdir()
        (tmp_path / "default" / "global.yaml").write_text(
            "name: Global\nentries: []\n"
        )
        # martin/ — owner-only (no explicit permissions)
        (tmp_path / "martin").mkdir()
        (tmp_path / "martin" / "private.yaml").write_text(
            "name: Private\nentries: []\n"
        )
        # martin/ — explicitly shared with alice (read-only)
        (tmp_path / "martin" / "shared.yaml").write_text(
            "name: Shared\nentries: []\npermissions:\n  alice:\n    read: true\n    write: false\n  martin:\n    read: true\n    write: true\n"
        )
        return tmp_path

    @pytest.fixture
    def service(self, watchlist_dir):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.watchlist.service import WatchlistService
        return WatchlistService(EventBus(), watchlist_dir)

    def _auth(self, username: str, role: str = "normal"):
        from portfolio_monitor.service.context import AuthContext
        return AuthContext(username=username, role=role)

    def test_admin_sees_all(self, service):
        wls = service.get_watchlists(self._auth("admin", "admin"))
        assert {wl.name for wl in wls} == {"Global", "Private", "Shared"}

    def test_default_watchlist_visible_to_everyone(self, service):
        for username in ("martin", "alice", "bob"):
            wls = service.get_watchlists(self._auth(username))
            names = {wl.name for wl in wls}
            assert "Global" in names, f"{username} should see Global"

    def test_owner_sees_own_watchlists(self, service):
        wls = service.get_watchlists(self._auth("martin"))
        names = {wl.name for wl in wls}
        assert "Private" in names
        assert "Shared" in names

    def test_unrelated_user_cannot_see_private(self, service):
        wls = service.get_watchlists(self._auth("alice"))
        names = {wl.name for wl in wls}
        assert "Private" not in names

    def test_explicitly_shared_read_visible_to_grantee(self, service):
        wls = service.get_watchlists(self._auth("alice"))
        names = {wl.name for wl in wls}
        assert "Shared" in names

    def test_unlisted_user_cannot_see_explicitly_shared(self, service):
        wls = service.get_watchlists(self._auth("bob"))
        names = {wl.name for wl in wls}
        assert "Shared" not in names

    def test_can_write_owner(self, service):
        wl = next(w for w in service.get_all_watchlists() if w.name == "Private")
        auth = self._auth("martin")
        assert service._can_write(wl, auth) is True

    def test_can_write_non_owner_denied(self, service):
        wl = next(w for w in service.get_all_watchlists() if w.name == "Private")
        assert service._can_write(wl, self._auth("alice")) is False

    def test_can_write_explicit_grant(self, service):
        wl = next(w for w in service.get_all_watchlists() if w.name == "Shared")
        assert service._can_write(wl, self._auth("martin")) is True

    def test_can_write_explicit_deny(self, service):
        wl = next(w for w in service.get_all_watchlists() if w.name == "Shared")
        assert service._can_write(wl, self._auth("alice")) is False

    def test_admin_can_write_anything(self, service):
        for wl in service.get_all_watchlists():
            assert service._can_write(wl, self._auth("admin", "admin")) is True

    def test_explicit_owner_in_yaml_overrides_folder(self, tmp_path):
        # A file in martin/ that declares owner: alice should be owned by alice.
        (tmp_path / "martin").mkdir()
        (tmp_path / "martin" / "override.yaml").write_text(
            "name: Override\nowner: alice\nentries: []\n"
        )
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.watchlist.service import WatchlistService
        svc = WatchlistService(EventBus(), tmp_path)
        wl = next(w for w in svc.get_all_watchlists() if w.name == "Override")
        assert wl.owner == "alice"
        assert wl.can("read", "alice") is True
        assert wl.can("read", "martin") is False


class TestPortfolioServiceFiltering:
    @pytest.fixture
    def portfolio_dir(self, tmp_path):
        # default/ — world-readable
        (tmp_path / "default").mkdir()
        (tmp_path / "default" / "global.yaml").write_text(
            "name: Global Portfolio\nstocks: []\n"
        )
        # martin/ — owner-only
        (tmp_path / "martin").mkdir()
        (tmp_path / "martin" / "private.yaml").write_text(
            "name: Martin Private\nstocks: []\n"
        )
        # martin/ — explicitly shared with alice (read-only)
        (tmp_path / "martin" / "shared.yaml").write_text(
            "name: Martin Shared\nstocks: []\npermissions:\n  alice:\n    read: true\n    write: false\n  martin:\n    read: true\n    write: true\n"
        )
        return tmp_path

    @pytest.fixture
    def service(self, portfolio_dir):
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.portfolio.service import PortfolioService
        return PortfolioService(EventBus(), portfolio_dir)

    def _auth(self, username: str, role: str = "normal"):
        from portfolio_monitor.service.context import AuthContext
        return AuthContext(username=username, role=role)

    def test_admin_sees_all(self, service):
        portfolios = service.get_portfolios(self._auth("admin", "admin"))
        assert {p.name for p in portfolios} == {"Global Portfolio", "Martin Private", "Martin Shared"}

    def test_default_visible_to_everyone(self, service):
        for username in ("martin", "alice", "bob"):
            portfolios = service.get_portfolios(self._auth(username))
            names = {p.name for p in portfolios}
            assert "Global Portfolio" in names

    def test_owner_sees_own_portfolios(self, service):
        portfolios = service.get_portfolios(self._auth("martin"))
        names = {p.name for p in portfolios}
        assert "Martin Private" in names
        assert "Martin Shared" in names

    def test_other_user_cannot_see_private(self, service):
        portfolios = service.get_portfolios(self._auth("alice"))
        names = {p.name for p in portfolios}
        assert "Martin Private" not in names

    def test_explicitly_shared_visible_to_grantee(self, service):
        portfolios = service.get_portfolios(self._auth("alice"))
        names = {p.name for p in portfolios}
        assert "Martin Shared" in names

    def test_unlisted_user_denied_explicit_permissions(self, service):
        portfolios = service.get_portfolios(self._auth("bob"))
        names = {p.name for p in portfolios}
        assert "Martin Shared" not in names

    def test_explicit_owner_in_yaml_overrides_folder(self, tmp_path):
        # A file in martin/ that declares owner: alice should be owned by alice.
        (tmp_path / "martin").mkdir()
        (tmp_path / "martin" / "override.yaml").write_text(
            "name: Override Portfolio\nowner: alice\nstocks: []\n"
        )
        from portfolio_monitor.core.events import EventBus
        from portfolio_monitor.portfolio.service import PortfolioService
        svc = PortfolioService(EventBus(), tmp_path)
        p = next(p for p in svc.get_all_portfolios() if p.name == "Override Portfolio")
        assert p.owner == "alice"
        assert p.can("read", "alice") is True
        assert p.can("read", "martin") is False
