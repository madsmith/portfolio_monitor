"""CLI commands for managing alert configurations for the current session user.

Subcommands:
  list               Show rules in the current alert configuration
  add                Add a new alert rule (ticker-specific or applies to all symbols)
  remove             Remove a rule by ID
  list-detectors     Show available detector kinds and their arguments
"""
import argparse
import json
import sys
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, render_table
from portfolio_monitor.cli.request import make_client


_ENDPOINT = "/api/v1/me/alert-config"


# ---------------------------------------------------------------------------
# Display models
# ---------------------------------------------------------------------------

class AlertRow(BaseModel):
    id:     Annotated[str, ColumnMeta("ID")]
    ticker: Annotated[str, ColumnMeta("Ticker")]
    kind:   Annotated[str, ColumnMeta("Kind")]
    args:   Annotated[str, ColumnMeta("Args")]


class DetectorArgRow(BaseModel):
    kind: Annotated[str, ColumnMeta("Kind")]
    arg:  Annotated[str, ColumnMeta("Arg")]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _alert_rows(config: dict[str, Any]) -> list[AlertRow]:
    rows: list[AlertRow] = []
    for rule in config.get("rules") or []:
        ticker = rule.get("ticker") or "(any)"
        kind = rule.get("kind", "")
        args = rule.get("args") or {}
        args_str = "  ".join(f"{k}={v}" for k, v in sorted(args.items())) if args else ""
        rows.append(AlertRow(
            id=rule.get("id", "")[:8],
            ticker=ticker,
            kind=kind,
            args=args_str,
        ))
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
    list_p = sub.add_parser("list", help="Show current alert rules")
    list_p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    list_p.set_defaults(func=_run_list)

    # add
    add_p = sub.add_parser(
        "add",
        help="Add an alert rule (use key=value pairs for args)",
        description=(
            "Add an alert rule.\n\n"
            "Examples:\n"
            "  alert add --kind percent_change threshold=0.05\n"
            "  alert add --kind percent_change --symbol NVDA threshold=0.08\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_p.add_argument("--kind", required=True, metavar="KIND", help="Detector kind (e.g. percent_change)")
    add_p.add_argument("--symbol", metavar="SYMBOL", help="Ticker to watch (omit to apply to all symbols)")
    add_p.add_argument("args", nargs="*", metavar="KEY=VALUE", help="Detector arguments as key=value pairs")
    add_p.set_defaults(func=_run_add)

    # remove
    rm_p = sub.add_parser("remove", help="Remove an alert rule by ID")
    rm_p.add_argument("id", metavar="ID", help="Rule ID or unique prefix to remove")
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
    config = client.get_json(_ENDPOINT)

    if args.json_out:
        print(json.dumps(config, indent=2))
        return

    rows = _alert_rows(config)
    if not rows:
        print("(no alert rules configured)")
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
    config: dict[str, Any] = client.get_json(_ENDPOINT)

    new_rule: dict[str, Any] = {
        "id": uuid4().hex,
        "ticker": args.symbol.upper() if args.symbol else "",
        "kind": args.kind,
        "args": detector_args,
    }
    config.setdefault("rules", []).append(new_rule)
    client.put_json(_ENDPOINT, json=config)

    scope = f"symbol '{args.symbol.upper()}'" if args.symbol else "all symbols"
    print(f"ok: added {args.kind} for {scope}  (id={new_rule['id'][:8]})")


def _run_remove(args: argparse.Namespace) -> None:
    client = make_client(args)
    config: dict[str, Any] = client.get_json(_ENDPOINT)

    prefix = args.id.lower()
    rules: list[dict[str, Any]] = config.get("rules") or []
    matches = [r for r in rules if r.get("id", "").startswith(prefix)]

    if not matches:
        print(f"error: no rule found with id prefix '{args.id}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"error: prefix '{args.id}' is ambiguous — matches {len(matches)} rules:", file=sys.stderr)
        for r in matches:
            print(f"  {r['id'][:8]}  {r.get('ticker') or '(any)'}  {r.get('kind')}", file=sys.stderr)
        sys.exit(1)

    rule = matches[0]
    config["rules"] = [r for r in rules if r.get("id") != rule["id"]]
    # cascade: remove overrides for this rule
    config["overrides"] = [
        o for o in (config.get("overrides") or [])
        if o.get("rule_id") != rule["id"]
    ]
    client.put_json(_ENDPOINT, json=config)

    scope = f"symbol '{rule['ticker']}'" if rule.get("ticker") else "all symbols"
    print(f"ok: removed {rule.get('kind')} for {scope}  (id={rule['id'][:8]})")


def _run_detectors(args: argparse.Namespace) -> None:
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
