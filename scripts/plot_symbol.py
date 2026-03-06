#!/usr/bin/env python3
"""Plot price and aggregate coverage for a symbol over the past 24 hours."""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow running from project root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.data.aggregate_cache import MemoryOnlyAggregateCache
from portfolio_monitor.data.provider import PolygonDataProvider
from portfolio_monitor.service.types import AssetSymbol, AssetTypes


async def fetch_and_plot(symbol: AssetSymbol, config: PortfolioMonitorConfig) -> None:
    cache = MemoryOnlyAggregateCache()
    provider = PolygonDataProvider(config, cache)

    now = datetime.now(ZoneInfo("UTC"))
    from_ = now - timedelta(hours=24)

    print(f"Fetching {symbol} from {from_.strftime('%Y-%m-%d %H:%M')} UTC to {now.strftime('%Y-%m-%d %H:%M')} UTC...")
    aggregates = await provider.get_range(symbol, from_, now, cache_write=False)
    print(f"Got {len(aggregates)} aggregates")

    if not aggregates:
        print("No data returned.")
        return

    # Build per-minute presence map
    total_minutes = int((now - from_).total_seconds() / 60)
    presence: list[int] = []
    times: list[datetime] = []

    agg_by_minute: dict[datetime, float] = {}
    for agg in aggregates:
        minute_key = agg.date_open.replace(second=0, microsecond=0)
        agg_by_minute[minute_key] = agg.close

    for i in range(total_minutes):
        minute = (from_ + timedelta(minutes=i)).replace(second=0, microsecond=0)
        times.append(minute)
        presence.append(1 if minute in agg_by_minute else 0)

    # Build price series (only where present)
    price_times = sorted(agg_by_minute.keys())
    prices = [agg_by_minute[t] for t in price_times]

    # Plot
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(14, 8),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )

    ax1.plot(price_times, prices, linewidth=1.0, color="steelblue")
    ax1.set_ylabel("Close Price")
    ax1.set_title(f"{symbol} — 24h Price")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(times, presence, step="post", alpha=0.8, color="steelblue")
    ax2.set_ylim(-0.1, 1.5)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["Missing", "Present"])
    ax2.set_ylabel("Coverage")
    _ET = ZoneInfo("America/New_York")
    ax2.set_xlabel("Time (ET)")
    ax2.grid(True, alpha=0.3)

    coverage_pct = sum(presence) / len(presence) * 100 if presence else 0
    ax2.set_title(f"Aggregate Coverage — {coverage_pct:.1f}% of minutes present")

    date_fmt = mdates.DateFormatter("%H:%M", tz=_ET)
    ax2.xaxis.set_major_formatter(date_fmt)
    ax2.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 10)))
    fig.autofmt_xdate(rotation=90, ha="center")

    plt.tight_layout()
    plt.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot 24h price data for a symbol")
    parser.add_argument("symbol", help="Ticker symbol (e.g. AAPL, BTC)")
    parser.add_argument(
        "--type",
        dest="asset_type",
        choices=["stock", "crypto", "currency"],
        default="stock",
        help="Asset type (default: stock)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config_path = Path("config/config.yaml")
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config = PortfolioMonitorConfig(config_path)

    asset_type = AssetTypes(args.asset_type)
    symbol = AssetSymbol(ticker=args.symbol.upper(), asset_type=asset_type)

    asyncio.run(fetch_and_plot(symbol, config))


if __name__ == "__main__":
    main()
