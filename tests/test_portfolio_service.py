"""PortfolioService ID allocation, against a real temporary database."""

import asyncio

import pytest

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.context import AuthContext

MARTIN = AuthContext(username="martin", role="normal")
KATARINA = AuthContext(username="katarina", role="normal")
LOT = {"quantity": 10, "purchase_price": 100, "purchase_date": "2024-01-02"}


@pytest.fixture
def db(tmp_path):
    database = AppDatabase(tmp_path / "app.db")
    database.initialize()
    yield database
    database.close()


@pytest.mark.asyncio
async def test_same_name_across_users_does_not_clobber(db):
    """Regression: IDs were sha256(name), so katarina's "Robinhood" took over martin's."""
    svc = PortfolioService(EventBus(), db)
    mine = svc.create_portfolio("Robinhood", MARTIN)
    assert svc.add_lot(mine.id, "stock", "AAPL", LOT, MARTIN) is not None
    await asyncio.sleep(0)  # let the AssetAdded publish task run

    theirs = svc.create_portfolio("Robinhood", KATARINA)
    assert theirs.id != mine.id

    reloaded = PortfolioService(EventBus(), db)
    p = reloaded.get_portfolio(mine.id, MARTIN)
    assert p is not None and p.owner == "martin"
    assert [a.symbol.ticker for a in p.assets()] == ["AAPL"]
    assert reloaded.get_portfolio(theirs.id, KATARINA).owner == "katarina"


def test_duplicate_names_same_user_get_distinct_ids(db):
    svc = PortfolioService(EventBus(), db)
    a = svc.create_portfolio("Same", MARTIN)
    b = svc.create_portfolio("Same", MARTIN)
    assert a.id != b.id
    assert len(a.id) == 16 and len(b.id) == 16
