"""CLI commands for managing alert configurations for the current session user.

Subcommands:
  list               Show current alert configuration
  add                Add or update a detector entry for a symbol or the default config
  remove             Remove a detector entry from the alert config
  list-detectors     Show available detector kinds and their arguments
"""
import argparse
import json
import sys
from typing import Annotated, Any

from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, render_table
from portfolio_monitor.cli.request import make_client


# ---------------------------------------------------------------------------
# Display models
# ---------------------------------------------------------------------------

class AlertRow(BaseModel):
    symbol: Annotated[str, ColumnMeta("Symbol")]
    kind:   Annotated[str, ColumnMeta("Kind")]
    args:   Annotated[str, ColumnMeta("Args")]


class DetectorArgRow(BaseModel):
    kind:   Annotated[str, ColumnMeta("Kind")]
    arg:    Annotated[str, ColumnMeta("Arg")]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _alert_rows(config: dict[str, Any]) -> list[AlertRow]:
    rows: list[AlertRow] = []
    for bucket_key in sorted(config.keys(), key=lambda k: ("" if k == "default" else k)):
        label = "(default)" if bucket_key == "default" else bucket_key
        detectors = config[bucket_key]
        if not isinstance(detectors, dict):
            continue
        for kind, args in sorted(detectors.items()):
            args_str = "  ".join(f"{k}={v}" for k, v in sorted(args.items())) if isinstance(args, dict) else str(args)
            rows.append(AlertRow(symbol=label, kind=kind, args=args_str))
    return rows


def _detector_rows(detectors: list[dict]) -> list[DetectorArgRow]:
    rows: list[DetectorArgRow] = []
    for d in detectors:
        kind = d["name"]
        args = d.get("args", [])
        if not args:
            rows.append(DetectorArgRow(kind=kind, arg="(no args)"))
        else:
            for idx, arg in enumerate(args):
                default = arg.get("default")
                default_str = "required" if "default" not in arg else f"default={default}"
                rows.append(DetectorArgRow(
                    kind="" if idx > 0 else kind,
                    arg=f"{arg['name']} ({arg['type']}, {default_str})",
                ))
    return rows


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def add_alerts_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("alert", help="Manage alert configuration for the current user")
    sub = p.add_subparsers(dest="alert_subcommand", metavar="SUBCOMMAND")
    sub.required = True

    # list
    list_p = sub.add_parser("list", help="Show current alert configuration")
    list_p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    list_p.set_defaults(func=_run_list)

    # add
    add_p = sub.add_parser(
        "add",
        help="Add or update a detector entry (use key=value pairs for args)",
        description=(
            "Add or update a detector in the alert config.\n\n"
            "Examples:\n"
            "  alert add --kind percent_change threshold=0.05\n"
            "  alert add --kind SMA_deviation --symbol NVDA threshold=0.08 period=2h\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_p.add_argument("--kind", required=True, metavar="KIND", help="Detector kind (e.g. percent_change)")
    add_p.add_argument("--symbol", metavar="SYMBOL", help="Symbol to configure (omit for default config)")
    add_p.add_argument("args", nargs="*", metavar="KEY=VALUE", help="Detector arguments as key=value pairs")
    add_p.set_defaults(func=_run_add)

    # remove
    rm_p = sub.add_parser("remove", help="Remove a detector entry from the alert config")
    rm_p.add_argument("--kind", required=True, metavar="KIND", help="Detector kind to remove")
    rm_p.add_argument("--symbol", metavar="SYMBOL", help="Symbol to remove from (omit for default config)")
    rm_p.set_defaults(func=_run_remove)

    # list-detectors
    det_p = sub.add_parser("list-detectors", help="Show available detector kinds and their arguments")
    det_p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    det_p.set_defaults(func=_run_detectors)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _run_list(args: argparse.Namespace) -> None:
    client = make_client(args)
    config = client.get_json("/api/v1/me/alerts")

    if args.json_out:
        print(json.dumps(config, indent=2))
        return

    rows = _alert_rows(config)
    if not rows:
        print("(no alerts configured)")
    else:
        render_table(rows)


def _run_add(args: argparse.Namespace) -> None:
    detector_args: dict[str, Any] = {}
    for kv in args.args:
        if "=" not in kv:
            print(f"error: argument '{kv}' must be in KEY=VALUE format", file=sys.stderr)
            sys.exit(1)
        key, _, raw_value = kv.partition("=")
        try:
            detector_args[key] = float(raw_value)
        except ValueError:
            detector_args[key] = raw_value

    client = make_client(args)
    config: dict[str, Any] = client.get_json("/api/v1/me/alerts")

    bucket = args.symbol if args.symbol else "default"
    if bucket not in config:
        config[bucket] = {}
    config[bucket][args.kind] = detector_args

    client.put_json("/api/v1/me/alerts", json=config)

    symbol_label = f"symbol '{args.symbol}'" if args.symbol else "default config"
    print(f"ok: set {args.kind} for {symbol_label}")


def _run_remove(args: argparse.Namespace) -> None:
    client = make_client(args)
    config: dict[str, Any] = client.get_json("/api/v1/me/alerts")

    bucket = args.symbol if args.symbol else "default"
    if bucket not in config or args.kind not in config.get(bucket, {}):
        symbol_label = f"symbol '{args.symbol}'" if args.symbol else "default config"
        print(f"error: {args.kind} not found in {symbol_label}", file=sys.stderr)
        sys.exit(1)

    del config[bucket][args.kind]
    # Remove empty symbol bucket (keep "default" even if empty)
    if not config[bucket] and bucket != "default":
        del config[bucket]

    client.put_json("/api/v1/me/alerts", json=config)

    symbol_label = f"symbol '{args.symbol}'" if args.symbol else "default config"
    print(f"ok: removed {args.kind} from {symbol_label}")


def _run_detectors(args: argparse.Namespace) -> None:
    # detectors endpoint is public — token not required
    client = make_client(args, require_token=False)
    detectors = client.get_json("/api/v1/detectors")

    if args.json_out:
        print(json.dumps(detectors, indent=2))
        return

    rows = _detector_rows(detectors)
    if not rows:
        print("(no detectors registered)")
    else:
        render_table(rows)
