import argparse
import json
import sys
from typing import Annotated

import httpx
from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, fmt_value, model_to_dict, render_table


class PriceRow(BaseModel):
    ticker:     Annotated[str,   ColumnMeta("Ticker")]
    asset_type: Annotated[str,   ColumnMeta("Type")]
    label:      Annotated[str,   ColumnMeta("Label")]
    price:      Annotated[float, ColumnMeta("Price", fmt="currency")]
    timestamp:  Annotated[str,   ColumnMeta("As of")]


class AggregateRow(BaseModel):
    timestamp: Annotated[str,    ColumnMeta("Time")]
    open:      Annotated[float,  ColumnMeta("Open",   fmt="currency")]
    high:      Annotated[float,  ColumnMeta("High",   fmt="currency")]
    low:       Annotated[float,  ColumnMeta("Low",    fmt="currency")]
    close:     Annotated[float,  ColumnMeta("Close",  fmt="currency")]
    volume:    Annotated[float,  ColumnMeta("Volume", fmt="volume")]


def add_price_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("price", help="Look up the current or previous-close price for a symbol")
    p.add_argument("ticker", metavar="TICKER", help="Asset ticker symbol (e.g. GOOG, BTC)")
    p.add_argument(
        "--type", "-t",
        dest="asset_type",
        default="stock",
        choices=["stock", "currency", "crypto"],
        metavar="TYPE",
        help="Asset type: stock (default), currency, or crypto",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--previous-close", "--prev", "-p",
        dest="previous_close",
        action="store_true",
        help="Return the previous session's closing price instead of the current price",
    )
    mode.add_argument(
        "--last",
        metavar="PERIOD",
        help="Return price history for the last PERIOD (e.g. 1h, 30m, 2d)",
    )
    p.add_argument(
        "--time",
        metavar="DATE_REF",
        help="Reference time for --last: unix timestamp or ISO date string (default: now)",
    )
    p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    p.set_defaults(func=run_price)


def run_price(args: argparse.Namespace) -> None:
    if not args.token:
        print("error: --token is required for price commands", file=sys.stderr)
        sys.exit(1)

    if args.last:
        _run_history(args)
    else:
        _run_single(args)


# ---------------------------------------------------------------------------
# Single price (current or previous-close)
# ---------------------------------------------------------------------------

def _run_single(args: argparse.Namespace) -> None:
    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.url.rstrip("/")
    path = f"/api/v1/price/{args.asset_type}/{args.ticker}"
    if args.previous_close:
        path += "/previous-close"

    try:
        response = httpx.get(f"{base}{path}", headers=headers)
    except httpx.ConnectError:
        print(f"error: could not connect to {base}", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 401:
        print("error: unauthorized — check your token", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 400:
        print(f"error: invalid asset type '{args.asset_type}'", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 404:
        print(f"error: price unavailable for {args.ticker} ({args.asset_type})", file=sys.stderr)
        sys.exit(1)
    if response.status_code != 200:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    data = response.json()
    row = PriceRow(
        ticker=args.ticker.upper(),
        asset_type=args.asset_type,
        label="Previous close" if args.previous_close else "Price",
        price=data["price"],
        timestamp=data["timestamp"],
    )

    if args.json_out:
        print(json.dumps(model_to_dict(row), indent=2))
        return

    print(
        f"{row.ticker} ({row.asset_type})  "
        f"{row.label}: {fmt_value(row.price, 'currency')}  "
        f"as of {row.timestamp}"
    )


# ---------------------------------------------------------------------------
# Price history (--last)
# ---------------------------------------------------------------------------

def _run_history(args: argparse.Namespace) -> None:
    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.url.rstrip("/")
    path = f"/api/v1/price/{args.asset_type}/{args.ticker}/history"
    params: dict[str, str] = {"last": args.last}
    if args.time:
        params["time"] = args.time

    try:
        response = httpx.get(f"{base}{path}", headers=headers, params=params)
    except httpx.ConnectError:
        print(f"error: could not connect to {base}", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 401:
        print("error: unauthorized — check your token", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 400:
        print(f"error: {response.json().get('error', response.text)}", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 404:
        print(f"error: no history available for {args.ticker} ({args.asset_type})", file=sys.stderr)
        sys.exit(1)
    if response.status_code != 200:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    data = response.json()

    if args.json_out:
        print(json.dumps(data, indent=2))
        return

    rows = [
        AggregateRow(
            timestamp=agg["timestamp"],
            open=agg["open"],
            high=agg["high"],
            low=agg["low"],
            close=agg["close"],
            volume=agg["volume"],
        )
        for agg in data["aggregates"]
    ]

    ticker = args.ticker.upper()
    print(f"{ticker} ({args.asset_type})  last {args.last}  {data['from']} → {data['to']}")
    render_table(rows)
