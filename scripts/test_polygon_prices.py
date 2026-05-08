"""
Standalone script to test Polygon price fetching for all portfolio and watchlist symbols.

Usage:
    .venv/bin/python scripts/test_polygon_prices.py

Tests get_aggregate() and get_previous_close() for every symbol found in the DB,
reporting timing and failures per symbol so you can see what's hanging.
"""
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add src to path so imports work without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.data import AggregateCache, PolygonDataProvider
from portfolio_monitor.data.database import AppDatabase

CONFIG_PATH = Path("config/config.yaml")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Show provider-level warnings without all the noise
logging.getLogger("portfolio_monitor.data.polygon").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


async def fetch_with_timeout(coro, timeout: float = 15.0):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"


async def main() -> None:
    config = PortfolioMonitorConfig(CONFIG_PATH)

    db = AppDatabase(config.datastore_path)
    db.initialize()

    # Collect all symbols from portfolios and watchlists
    portfolio_symbols = {
        asset.symbol
        for portfolio in db.portfolios.get_all()
        for asset in portfolio.assets()
    }
    watchlist_symbols = {
        entry.symbol
        for wl in db.watchlists.get_all()
        for entry in wl.entries
    }
    all_symbols = portfolio_symbols | watchlist_symbols

    logger.info(
        "Found %d portfolio symbols, %d watchlist symbols, %d total unique",
        len(portfolio_symbols), len(watchlist_symbols), len(all_symbols),
    )
    if not all_symbols:
        logger.error("No symbols found — check that config/app_data.db has data")
        return

    cache = AggregateCache(config.aggregate_cache_path)
    cache.initialize()
    await cache.load()

    provider = PolygonDataProvider(config, cache)

    print()
    print(f"{'Symbol':<12} {'Type':<10} {'Method':<18} {'Result':<12} {'Time':>7}")
    print("-" * 65)

    for symbol in sorted(all_symbols, key=lambda s: s.ticker):
        label = symbol.ticker
        asset_type = str(symbol.asset_type.value) if hasattr(symbol.asset_type, "value") else str(symbol.asset_type)

        for method_name, coro_fn in [
            ("get_aggregate", lambda s=symbol: provider.get_aggregate(s)),
            ("get_previous_close", lambda s=symbol: provider.get_previous_close(s)),
        ]:
            t0 = time.monotonic()
            result = await fetch_with_timeout(coro_fn(), timeout=20.0)
            elapsed = time.monotonic() - t0

            if isinstance(result, str):
                outcome = result  # TIMEOUT or ERROR: ...
            elif result is None:
                outcome = "None"
            else:
                outcome = f"{result.close:.4f}"

            flag = " <-- SLOW" if elapsed > 5 else ""
            print(f"{label:<12} {asset_type:<10} {method_name:<18} {outcome:<12} {elapsed:>6.1f}s{flag}")

    print()
    await cache.close()
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
