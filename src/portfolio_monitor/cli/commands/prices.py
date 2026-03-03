import argparse
import sys

import httpx


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
    p.add_argument(
        "--previous-close", "--prev", "-p",
        dest="previous_close",
        action="store_true",
        help="Return the previous session's closing price instead of the current price",
    )
    p.set_defaults(func=run_price)


def run_price(args: argparse.Namespace) -> None:
    if not args.token:
        print("error: --token is required for price commands", file=sys.stderr)
        sys.exit(1)

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
    label = "Previous close" if args.previous_close else "Price"
    price = data["price"]
    timestamp = data["timestamp"]
    print(f"{args.ticker.upper()} ({args.asset_type})  {label}: ${price:,.6g}  as of {timestamp}")
