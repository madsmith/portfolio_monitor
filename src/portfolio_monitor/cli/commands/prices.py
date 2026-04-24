import argparse
import json
import sys
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from portfolio_monitor.cli.request import make_client
from portfolio_monitor.cli.display import ColumnMeta, render_table
from portfolio_monitor.data.timespan import AggregateTimespan, Timespan

_ET = ZoneInfo("America/New_York")
_DAY_SPANS = {Timespan.DAY, Timespan.WEEK, Timespan.MONTH, Timespan.QUARTER, Timespan.YEAR}


def _fmt_ts(iso: str, span: AggregateTimespan) -> str:
    dt = datetime.fromisoformat(iso).astimezone(_ET)
    if span.timespan in _DAY_SPANS:
        return dt.date().isoformat()
    return dt.isoformat(timespec="minutes")


class PriceOutput(BaseModel):
    """OHLCV output; symbol is included for single-candle responses."""
    symbol:    dict[str, str]
    timestamp: str
    open:      float
    high:      float
    low:       float
    close:     float
    price:     float
    volume:    float


class OpenCloseOutput(BaseModel):
    """Session OHLCV output including pre-market and after-hours prices."""
    symbol:      dict[str, str]
    date:        str
    open:        float
    high:        float
    low:         float
    close:       float | None  # None during an active session
    price:       float | None  # None during an active session
    volume:      float
    pre_market:  float | None
    after_hours: float | None


class AggregateRow(BaseModel):
    timestamp:   Annotated[str,         ColumnMeta("Time")]
    open:        Annotated[float,        ColumnMeta("Open",         fmt="currency")]
    high:        Annotated[float,        ColumnMeta("High",         fmt="currency")]
    low:         Annotated[float,        ColumnMeta("Low",          fmt="currency")]
    close:       Annotated[float,        ColumnMeta("Close",        fmt="currency")]
    volume:      Annotated[float,        ColumnMeta("Volume",       fmt="volume")]


class OpenCloseRow(BaseModel):
    date:        Annotated[str,          ColumnMeta("Date")]
    open:        Annotated[float,        ColumnMeta("Open",         fmt="currency")]
    high:        Annotated[float,        ColumnMeta("High",         fmt="currency")]
    low:         Annotated[float,        ColumnMeta("Low",          fmt="currency")]
    close:       Annotated[float | None, ColumnMeta("Close",        fmt="currency")]
    volume:      Annotated[float,        ColumnMeta("Volume",       fmt="volume")]
    pre_market:  Annotated[float | None, ColumnMeta("Pre-Market",   fmt="currency")]
    after_hours: Annotated[float | None, ColumnMeta("After-Hours",  fmt="currency")]


def add_price_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "price",
        help="Look up OHLCV data for a symbol",
        usage=(
            "%(prog)s [--previous-close] [--json] [-t TYPE] TICKER\n"
            "       %(prog)s [--open-close] [--time DATE_REF] [--json] [-t TYPE] TICKER\n"
            "       %(prog)s [--last PERIOD] [--span SPAN] [--time DATE_REF] [--json] [-t TYPE] TICKER"
        ),
    )
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
        help="Return the previous session's OHLCV (standalone; incompatible with history options)",
    )
    p.add_argument(
        "--open-close",
        dest="open_close",
        action="store_true",
        help="Return the session OHLCV with pre-market and after-hours prices. "
             "Use --time to specify the date (default: today).",
    )
    history = p.add_argument_group("history options")
    history.add_argument(
        "--last",
        metavar="PERIOD",
        help="Return candles covering PERIOD ending at --time (e.g. 1mo, 3mo, 7d). "
             "Omit to return a single candle.",
    )
    history.add_argument(
        "--span",
        default=None,
        metavar="SPAN",
        help="Candle size (default: 1m). Examples: 1m, 5m, 15m, 1h, 4h, 1d, 7d",
    )
    history.add_argument(
        "--time",
        metavar="DATE_REF",
        help="End of the query window: unix timestamp or ISO date string (default: now)",
    )
    p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    p.set_defaults(func=run_price)


def run_price(args: argparse.Namespace) -> None:
    client = make_client(args)

    if args.previous_close and args.open_close:
        print("error: --previous-close and --open-close are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.previous_close:
        if args.span or args.time:
            print("error: --previous-close cannot be combined with --span or --time", file=sys.stderr)
            sys.exit(1)
        _run_previous_close(client, args)
        return

    if args.open_close:
        if args.span or args.last:
            print("error: --open-close cannot be combined with --span or --last", file=sys.stderr)
            sys.exit(1)
        _run_open_close(client, args)
        return

    path = f"/api/v1/price/{args.asset_type}/{args.ticker}/history"

    try:
        span = AggregateTimespan.parse(args.span or "1m")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    params: dict[str, str] = {"span": str(span)}
    if args.last:
        params["last"] = args.last
    if args.time:
        params["time"] = args.time

    response = client.get(path, params=params)
    if response.status_code == 400:
        print(f"error: {response.json().get('error', response.text)}", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 404:
        print(f"error: no data available for {args.ticker} ({args.asset_type})", file=sys.stderr)
        sys.exit(1)
    if not response.is_success:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    data = response.json()
    aggs = data["aggregates"]

    if args.json_out:
        symbol = {"ticker": args.ticker.upper(), "type": args.asset_type}
        if args.last:
            outputs = [
                PriceOutput(
                    symbol=symbol,
                    timestamp=agg["timestamp"],
                    open=agg["open"],
                    high=agg["high"],
                    low=agg["low"],
                    close=agg["close"],
                    price=agg["close"],
                    volume=agg["volume"],
                )
                for agg in aggs
            ]
            print(json.dumps([o.model_dump() for o in outputs], indent=2))
        else:
            agg = aggs[0]
            out = PriceOutput(
                symbol=symbol,
                timestamp=agg["timestamp"],
                open=agg["open"],
                high=agg["high"],
                low=agg["low"],
                close=agg["close"],
                price=agg["close"],
                volume=agg["volume"],
            )
            print(out.model_dump_json(indent=2))
        return


    rows = [
        AggregateRow(
            timestamp=_fmt_ts(agg["timestamp"], span),
            open=agg["open"],
            high=agg["high"],
            low=agg["low"],
            close=agg["close"],
            volume=agg["volume"],
        )
        for agg in aggs
    ]

    render_table(rows)


def _run_previous_close(client, args: argparse.Namespace) -> None:
    path = f"/api/v1/price/{args.asset_type}/{args.ticker}/previous-close"
    response = client.get(path)
    if response.status_code == 404:
        print(f"error: price unavailable for {args.ticker} ({args.asset_type})", file=sys.stderr)
        sys.exit(1)
    if not response.is_success:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    data = response.json()

    out = PriceOutput(
        symbol={"ticker": args.ticker.upper(), "type": args.asset_type},
        timestamp=data["timestamp"],
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        price=data["close"],
        volume=data["volume"],
    )

    if args.json_out:
        print(out.model_dump_json(indent=2))
        return

    span = AggregateTimespan.parse("1d")
    render_table([AggregateRow(
        timestamp=_fmt_ts(out.timestamp, span),
        open=out.open,
        high=out.high,
        low=out.low,
        close=out.close,
        volume=out.volume,
    )])


def _run_open_close(client, args: argparse.Namespace) -> None:
    path = f"/api/v1/price/{args.asset_type}/{args.ticker}/open-close"
    params: dict[str, str] = {}
    if args.time:
        params["date"] = args.time

    response = client.get(path, params=params)
    if response.status_code == 404:
        print(f"error: no data available for {args.ticker} ({args.asset_type})", file=sys.stderr)
        sys.exit(1)
    if not response.is_success:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    data = response.json()

    out = OpenCloseOutput(
        symbol={"ticker": args.ticker.upper(), "type": args.asset_type},
        date=data["date"],
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        price=data["close"],
        volume=data["volume"],
        pre_market=data.get("pre_market"),
        after_hours=data.get("after_hours"),
    )

    if args.json_out:
        print(out.model_dump_json(indent=2))
        return

    render_table([OpenCloseRow(
        date=out.date,
        open=out.open,
        high=out.high,
        low=out.low,
        close=out.close,
        volume=out.volume,
        pre_market=out.pre_market,
        after_hours=out.after_hours,
    )])
