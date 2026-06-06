"""Live integration tests for MassiveProvider.

These tests hit the real Massive API and require valid credentials in
config/config_private.yaml.  They are skipped automatically when the
key is absent.

Run all:
    .venv/bin/python -m pytest tests/data/providers/test_massive.py -v -s

Run a single test:
    .venv/bin/python -m pytest tests/data/providers/test_massive.py::test_get_aggregate -v -s
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.data.providers.massive import MassiveProvider
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def config() -> PortfolioMonitorConfig:
    return PortfolioMonitorConfig(ROOT / "config" / "config.yaml")


@pytest.fixture(scope="module")
def provider(config: PortfolioMonitorConfig) -> MassiveProvider:
    if not config.massive_api_key:
        pytest.skip("Massive API key not configured")
    return MassiveProvider(config)


@pytest.fixture
def aapl() -> AssetSymbol:
    return AssetSymbol("AAPL", AssetTypes.Stock)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_aggregate(provider: MassiveProvider, aapl: AssetSymbol) -> None:
    """get_aggregate returns a recent 1-min bar or None outside market hours."""
    agg = await provider.get_aggregate(aapl)
    if agg is None:
        pytest.skip("No recent bar available (market may be closed)")
    print(f"\n  {aapl.ticker}  o={agg.open}  h={agg.high}  l={agg.low}  c={agg.close}  vol={agg.volume}")
    print(f"  date_open={agg.date_open}  timespan={agg.timespan}")
    assert agg.symbol == aapl
    assert agg.open > 0
    assert agg.close > 0
    assert agg.timespan == timedelta(minutes=1)
    assert agg.date_open.tzinfo is not None


@pytest.mark.asyncio
async def test_get_previous_close(provider: MassiveProvider, aapl: AssetSymbol) -> None:
    """get_previous_close returns a daily-timespan aggregate."""
    agg = await provider.get_previous_close(aapl)
    assert agg is not None, "Expected a previous close aggregate"
    print(f"\n  {aapl.ticker} prev close  c={agg.close}  date={agg.date_open.date()}")
    assert agg.symbol == aapl
    assert agg.close > 0
    assert agg.date_open.tzinfo is not None


@pytest.mark.asyncio
async def test_get_range(provider: MassiveProvider, aapl: AssetSymbol) -> None:
    """get_range returns 1-min bars covering yesterday's last 2 hours of trading."""
    now = datetime.now(timezone.utc)
    to = (now - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    from_ = to - timedelta(hours=2)
    bars = await provider.get_range(aapl, from_, to)
    print(f"\n  {aapl.ticker} 1m range {from_.strftime('%H:%M')}→{to.strftime('%H:%M')} UTC (yesterday): {len(bars)} bars")
    if bars:
        print(f"  first={bars[0].date_open.strftime('%H:%M')}  last={bars[-1].date_open.strftime('%H:%M')}")
    assert isinstance(bars, list)
    assert len(bars) > 0, "Expected bars for a past market session"
    for bar in bars:
        assert bar.symbol == aapl
        assert bar.timespan == timedelta(minutes=1)


@pytest.mark.asyncio
async def test_get_open_close(provider: MassiveProvider, aapl: AssetSymbol) -> None:
    """get_open_close returns a daily aggregate for yesterday."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    agg = await provider.get_open_close(aapl, yesterday)
    if agg is None:
        pytest.skip("No daily bar for yesterday (weekend/holiday?)")
    print(f"\n  {aapl.ticker} daily  o={agg.open}  c={agg.close}  vol={agg.volume}  date={agg.date_open.date()}")
    assert agg.symbol == aapl
    assert agg.open > 0
    assert agg.close > 0


@pytest.mark.asyncio
async def test_get_daily_range(provider: MassiveProvider, aapl: AssetSymbol) -> None:
    """get_daily_range returns daily bars for the past 7 days."""
    to = datetime.now(timezone.utc)
    from_ = to - timedelta(days=7)
    bars = await provider.get_daily_range(aapl, from_, to)
    print(f"\n  {aapl.ticker} daily range (last 7 days): {len(bars)} bars")
    if bars:
        print(f"  first={bars[0].date_open.date()}  c={bars[0].close}")
        print(f"  last ={bars[-1].date_open.date()}  c={bars[-1].close}")
    assert isinstance(bars, list)
    assert len(bars) > 0, "Expected at least one daily bar in a 7-day window"
    for bar in bars:
        assert bar.symbol == aapl
        assert bar.close > 0
