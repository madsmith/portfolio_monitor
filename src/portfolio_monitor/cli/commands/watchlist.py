"""CLI commands for managing watchlists.

Subcommands:
  list                         List all watchlists
  show   ID                    Show watchlist detail
  create --name NAME           Create a new watchlist
  delete ID                    Delete a watchlist
  add    ID --ticker T         Add an entry
  remove ID --ticker T         Remove an entry
  note   ID --ticker T TEXT    Set notes on an entry
  target ID --ticker T         Set buy/sell price targets
  meta   ID --ticker T K=V     Set metadata key(s) on an entry
  alert show   ID --ticker T              Show entry alert config
  alert set    ID --ticker T --kind K ... Set an alert on an entry
  alert remove ID --ticker T --kind K     Remove an alert from an entry
"""

import argparse
import json
import sys
from typing import Annotated, Any

from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, fmt_value, render_table
from portfolio_monitor.cli.request import APIClient, make_client


# ---------------------------------------------------------------------------
# Display models
# ---------------------------------------------------------------------------

class WatchlistSummaryRow(BaseModel):
    id:          Annotated[str, ColumnMeta("ID")]
    name:        Annotated[str, ColumnMeta("Name")]
    owner:       Annotated[str, ColumnMeta("Owner")]
    entry_count: Annotated[int, ColumnMeta("Entries", fmt="right")]


class WatchlistEntryRow(BaseModel):
    ticker:        Annotated[str,        ColumnMeta("Ticker", min_width=8)]
    asset_type:    Annotated[str,        ColumnMeta("Type")]
    current_price: Annotated[float|None, ColumnMeta("Price",    fmt="currency")]
    notes:         Annotated[str,        ColumnMeta("Notes")]
    target_buy:    Annotated[float|None, ColumnMeta("Buy",      fmt="currency")]
    target_sell:   Annotated[float|None, ColumnMeta("Sell",     fmt="currency")]
    time_added:    Annotated[str|None,   ColumnMeta("Added",    json_only=True)]
    initial_price: Annotated[float|None, ColumnMeta("Init$",    fmt="currency", json_only=True)]
    meta:          Annotated[dict,       ColumnMeta("Meta",     json_only=True)]
    alerts:        Annotated[dict,       ColumnMeta("Alerts",   json_only=True)]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def add_watchlist_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("watchlist", help="Manage watchlists")
    p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    sub = p.add_subparsers(dest="wl_command", metavar="SUBCOMMAND")
    sub.required = True

    # list
    sub.add_parser("list", help="List all watchlists")

    # show
    s = sub.add_parser("show", help="Show watchlist detail")
    s.add_argument("id", metavar="ID")

    # create
    s = sub.add_parser("create", help="Create a new watchlist")
    s.add_argument("--name", required=True, metavar="NAME")

    # delete
    s = sub.add_parser("delete", help="Delete a watchlist")
    s.add_argument("id", metavar="ID")

    # add entry
    s = sub.add_parser("add", help="Add an entry to a watchlist")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("--type", dest="asset_type", default="stock",
                   choices=["stock", "currency", "crypto"])
    s.add_argument("--notes", default="", metavar="TEXT")
    s.add_argument("--buy", dest="target_buy", type=float, default=None, metavar="PRICE")
    s.add_argument("--sell", dest="target_sell", type=float, default=None, metavar="PRICE")

    # remove entry
    s = sub.add_parser("remove", help="Remove an entry from a watchlist")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")

    # note
    s = sub.add_parser("note", help="Set notes on an entry")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("text", metavar="TEXT")

    # target
    s = sub.add_parser("target", help="Set price targets on an entry")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("--buy", dest="target_buy", type=float, default=None, metavar="PRICE")
    s.add_argument("--sell", dest="target_sell", type=float, default=None, metavar="PRICE")

    # meta
    s = sub.add_parser("meta", help="Set metadata key(s) on an entry (KEY=VALUE ...)")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("pairs", nargs="+", metavar="KEY=VALUE")

    # alert sub-group
    al = sub.add_parser("alert", help="Manage alerts on watchlist entries")
    al_sub = al.add_subparsers(dest="alert_command", metavar="SUBCOMMAND")
    al_sub.required = True

    s = al_sub.add_parser("show", help="Show alert config for an entry")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")

    s = al_sub.add_parser("set", help="Add/update a detector on an entry (KEY=VALUE ...)")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("--kind", required=True, metavar="KIND")
    s.add_argument("args", nargs="*", metavar="KEY=VALUE")

    s = al_sub.add_parser("remove", help="Remove a detector from an entry")
    s.add_argument("id", metavar="ID")
    s.add_argument("--ticker", required=True, metavar="TICKER")
    s.add_argument("--kind", required=True, metavar="KIND")

    p.set_defaults(func=run_watchlist)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_kvpairs(pairs: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"Invalid KEY=VALUE: {pair}", file=sys.stderr)
            sys.exit(1)
        k, v = pair.split("=", 1)
        # Try to coerce to float or int
        try:
            result[k] = float(v) if "." in v else int(v)
        except ValueError:
            result[k] = v
    return result


def _print_detail(watchlist: dict, json_out: bool) -> None:
    if json_out:
        print(json.dumps(watchlist, indent=2))
        return
    print(f"Watchlist: {watchlist['name']}  (id: {watchlist['id']}, owner: {watchlist['owner']})")
    entries = watchlist.get("entries", [])
    if not entries:
        print("  (no entries)")
        return
    rows = [WatchlistEntryRow(**e) for e in entries]
    render_table(rows, indent="  ")


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def run_watchlist(args: argparse.Namespace) -> None:
    client = make_client(args)
    cmd = args.wl_command

    if cmd == "list":
        _cmd_list(client, args)
    elif cmd == "show":
        _cmd_show(client, args)
    elif cmd == "create":
        _cmd_create(client, args)
    elif cmd == "delete":
        _cmd_delete(client, args)
    elif cmd == "add":
        _cmd_add(client, args)
    elif cmd == "remove":
        _cmd_remove(client, args)
    elif cmd == "note":
        _cmd_note(client, args)
    elif cmd == "target":
        _cmd_target(client, args)
    elif cmd == "meta":
        _cmd_meta(client, args)
    elif cmd == "alert":
        _cmd_alert(client, args)
    else:
        print(f"Unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _cmd_list(client: APIClient, args: argparse.Namespace) -> None:
    data = client.get_json("/api/v1/watchlists")
    assert isinstance(data, list)
    if args.json_out:
        print(json.dumps(data, indent=2))
        return
    if not data:
        print("No watchlists found.")
        return
    rows = [WatchlistSummaryRow(**w) for w in data]
    render_table(rows)


def _cmd_show(client: APIClient, args: argparse.Namespace) -> None:
    data = client.get_json(f"/api/v1/watchlist/{args.id}")
    assert isinstance(data, dict)
    # Backfill current_price from previous-close for entries with no live price
    for entry in data.get("entries", []):
        if entry.get("current_price") is None:
            price_data = client.try_get_json(
                f"/api/v1/price/{entry['asset_type']}/{entry['ticker']}/previous-close"
            )
            if price_data and price_data.get("price") is not None:
                entry["current_price"] = price_data["price"]
    _print_detail(data, args.json_out)


def _cmd_create(client: APIClient, args: argparse.Namespace) -> None:
    resp = client.post("/api/v1/watchlist", json={"name": args.name})
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    _print_detail(data, args.json_out)


def _cmd_delete(client: APIClient, args: argparse.Namespace) -> None:
    resp = client.delete(f"/api/v1/watchlist/{args.id}")
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    if args.json_out:
        print(resp.text)
    else:
        print(f"Deleted watchlist {args.id}")


def _cmd_add(client: APIClient, args: argparse.Namespace) -> None:
    body: dict[str, Any] = {"ticker": args.ticker.upper(), "asset_type": args.asset_type}
    if args.notes:
        body["notes"] = args.notes
    if args.target_buy is not None:
        body["target_buy"] = args.target_buy
    if args.target_sell is not None:
        body["target_sell"] = args.target_sell
    resp = client.post(f"/api/v1/watchlist/{args.id}/entries", json=body)
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    _print_detail(resp.json(), args.json_out)


def _cmd_remove(client: APIClient, args: argparse.Namespace) -> None:
    resp = client.delete(f"/api/v1/watchlist/{args.id}/entries/{args.ticker.upper()}")
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    _print_detail(resp.json(), args.json_out)


def _cmd_note(client: APIClient, args: argparse.Namespace) -> None:
    resp = client.put(
        f"/api/v1/watchlist/{args.id}/entries/{args.ticker.upper()}",
        json={"notes": args.text},
    )
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    _print_detail(resp.json(), args.json_out)


def _cmd_target(client: APIClient, args: argparse.Namespace) -> None:
    body: dict[str, Any] = {}
    if args.target_buy is not None:
        body["target_buy"] = args.target_buy
    if args.target_sell is not None:
        body["target_sell"] = args.target_sell
    if not body:
        print("Specify --buy and/or --sell", file=sys.stderr)
        sys.exit(1)
    resp = client.put(f"/api/v1/watchlist/{args.id}/entries/{args.ticker.upper()}", json=body)
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    _print_detail(resp.json(), args.json_out)


def _cmd_meta(client: APIClient, args: argparse.Namespace) -> None:
    patch = _parse_kvpairs(args.pairs)
    resp = client.put(
        f"/api/v1/watchlist/{args.id}/entries/{args.ticker.upper()}",
        json={"meta": patch},
    )
    if not resp.is_success:
        print(f"Error: {resp.text}", file=sys.stderr)
        sys.exit(1)
    _print_detail(resp.json(), args.json_out)


def _cmd_alert(client: APIClient, args: argparse.Namespace) -> None:
    base = f"/api/v1/watchlist/{args.id}/entries/{args.ticker.upper()}/alerts"
    cmd = args.alert_command

    if cmd == "show":
        data = client.get_json(base)
        if args.json_out:
            print(json.dumps(data, indent=2))
        else:
            if not data:
                print("No alerts configured.")
            else:
                for kind, kargs in data.items():
                    print(f"  {kind}: {kargs}")

    elif cmd == "set":
        # Get current alerts, merge in the new one, then PUT
        current = client.get_json(base)
        assert isinstance(current, dict)
        current[args.kind] = _parse_kvpairs(args.args)
        resp = client.put(base, json=current)
        if not resp.is_success:
            print(f"Error: {resp.text}", file=sys.stderr)
            sys.exit(1)
        if args.json_out:
            print(resp.text)
        else:
            print(f"Alert '{args.kind}' set on {args.ticker.upper()}")

    elif cmd == "remove":
        current = client.get_json(base)
        assert isinstance(current, dict)
        current.pop(args.kind, None)
        resp = client.put(base, json=current)
        if not resp.is_success:
            print(f"Error: {resp.text}", file=sys.stderr)
            sys.exit(1)
        if args.json_out:
            print(resp.text)
        else:
            print(f"Alert '{args.kind}' removed from {args.ticker.upper()}")
