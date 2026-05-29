"""CLI commands for managing alert configurations for the current session user.

Subcommands:
  list               Show rules in the current alert configuration
  show               Show detailed info for a single rule, including exclusions
  add                Add a new alert rule (ticker-specific or global with optional scope)
  edit               Mute, unmute, enable, disable, or manage exclusions for a rule
  remove             Remove a rule by ID
  list-detectors     Show available detector kinds and their arguments
"""
import argparse
import json
import shutil
import sys
import textwrap
from typing import Annotated, Any

from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, render_table
from portfolio_monitor.cli.utils import help_on_error
from portfolio_monitor.cli.request import make_client


_ENDPOINT = "/api/v1/me/alert-config"
_RULES_ENDPOINT = "/api/v1/me/alert-config/rules"



# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class AlertRuleOut(BaseModel):
    id:         str
    ticker:     str | None
    asset_type: str | None
    kind:       str
    args:       dict[str, Any]
    enabled:    bool
    muted_until: str | None


class AlertRow(BaseModel):
    id:         Annotated[str, ColumnMeta("ID")]
    ticker:     Annotated[str, ColumnMeta("Ticker")]
    scope:      Annotated[str, ColumnMeta("Scope")]
    kind:       Annotated[str, ColumnMeta("Kind")]
    args:       Annotated[str, ColumnMeta("Args")]
    status:     Annotated[str, ColumnMeta("Status")]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _rule_out(rule: dict[str, Any]) -> AlertRuleOut:
    return AlertRuleOut(
        id=rule["id"],
        ticker=rule.get("ticker") or None,
        asset_type=rule.get("asset_type") or None,
        kind=rule["kind"],
        args=rule.get("args") or {},
        enabled=bool(rule.get("enabled", True)),
        muted_until=rule.get("muted_until"),
    )


def _alert_rows(config: dict[str, Any]) -> list[AlertRow]:
    rows: list[AlertRow] = []
    for rule in config.get("rules") or []:
        ticker = rule.get("ticker") or ""
        asset_type = rule.get("asset_type") or ""
        if ticker:
            scope = asset_type or "any"
            ticker_display = ticker
        else:
            ticker_display = "(global)"
            scope = asset_type or "all"
        kind = rule.get("kind", "")
        args = rule.get("args") or {}
        args_str = "  ".join(f"{k}={v}" for k, v in sorted(args.items())) if args else ""
        enabled = rule.get("enabled", True)
        muted_until = rule.get("muted_until")
        if not enabled:
            status = "disabled"
        elif muted_until:
            status = "muted"
        else:
            status = "on"
        rows.append(AlertRow(
            id=rule.get("id", "")[:8],
            ticker=ticker_display,
            scope=scope,
            kind=kind,
            args=args_str,
            status=status,
        ))
    return rows


def _arg_spec(arg: dict) -> str:
    options = arg.get("options")
    type_str = "|".join(options) if options else arg["type"]
    default_str = "required)" if "default" not in arg else f"default={arg['default']})"
    return f"    {arg['name']} ({type_str}, {default_str}"


def _print_detectors(detectors: list[dict]) -> None:
    term_width = shutil.get_terminal_size((100, 24)).columns

    left_col = max(
        max(len(d["name"]) for d in detectors),
        max(
            (len(_arg_spec(arg)) for d in detectors for arg in d.get("args", [])),
            default=0,
        ),
    ) + 2

    desc_width = max(term_width - left_col, 20)
    cont_pad = " " * left_col

    for idx, d in enumerate(detectors):
        if idx:
            print()

        desc_lines = textwrap.wrap(d.get("description", ""), desc_width)
        print(f"{d['name']:<{left_col}}{desc_lines[0] if desc_lines else ''}")
        for line in desc_lines[1:]:
            print(f"{cont_pad}{line}")

        for arg in d.get("args", []):
            spec = _arg_spec(arg)
            adesc_lines = textwrap.wrap(arg.get("description", ""), desc_width)
            print(f"{spec:<{left_col}}{adesc_lines[0] if adesc_lines else ''}")
            for line in adesc_lines[1:]:
                print(f"{cont_pad}{line}")


def _print_rule_detail(rule: dict[str, Any]) -> None:
    """Print a formatted single-rule detail view."""
    r = _rule_out(rule)
    ticker = rule.get("ticker") or ""
    asset_type = rule.get("asset_type") or ""
    if ticker:
        scope = asset_type or "any"
        ticker_display = ticker
    else:
        ticker_display = "(global)"
        scope = asset_type or "all"

    if not r.enabled:
        status = "disabled"
    elif r.muted_until:
        status = f"muted until {r.muted_until}"
    else:
        status = "on"

    args_str = "  ".join(f"{k}={v}" for k, v in sorted(r.args.items())) if r.args else "(none)"

    print(f"ID:         {r.id}")
    print(f"Ticker:     {ticker_display}")
    print(f"Scope:      {scope}")
    print(f"Kind:       {r.kind}")
    print(f"Args:       {args_str}")
    print(f"Status:     {status}")

    exclusions: list[dict[str, Any]] = rule.get("excluded_tickers") or []
    if exclusions:
        print(f"Exclusions:")
        for ex in exclusions:
            print(f"  {ex.get('ticker', '')}  ({ex.get('asset_type', '')})")
    else:
        print(f"Exclusions: (none)")


def _resolve_rule(client, prefix: str) -> dict[str, Any]:
    """Fetch all rules and return the one matching the given ID prefix."""
    config: dict[str, Any] = client.get_json(_ENDPOINT)
    rules: list[dict[str, Any]] = config.get("rules") or []
    prefix = prefix.lower()
    matches = [r for r in rules if r.get("id", "").startswith(prefix)]
    if not matches:
        print(f"error: no rule found with id prefix '{prefix}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"error: prefix '{prefix}' is ambiguous — matches {len(matches)} rules:", file=sys.stderr)
        for r in matches:
            print(f"  {r['id'][:8]}  {r.get('ticker') or '(global)'}  {r.get('kind')}", file=sys.stderr)
        sys.exit(1)
    return matches[0]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def add_alerts_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("alert", help="Manage alert configuration for the current user")
    help_on_error(p)
    sub = p.add_subparsers(dest="alert_subcommand", metavar="SUBCOMMAND")
    sub.required = True

    # list
    list_p = sub.add_parser("list", help="Show current alert rules")
    list_p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    list_p.set_defaults(func=_run_list)

    # show
    show_p = sub.add_parser("show", help="Show detailed info for a single rule")
    help_on_error(show_p)
    show_p.add_argument("id", metavar="ID", help="Rule ID or unique prefix")
    show_p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON")
    show_p.set_defaults(func=_run_show)

    # add
    add_p = sub.add_parser(
        "add",
        help="Add an alert rule (use key=value pairs for args)",
        description=(
            "Add an alert rule.\n\n"
            "Examples:\n"
            "  - Global rule (all assets):\n"
            "      alert add --kind percent_change threshold=0.05\n"
            "  - Global rule (crypto type assets only):\n"
            "      alert add --kind percent_change --asset-type CRYPTO threshold=0.08\n"
            "  - Ticker rule (specific asset, stock is implicit):\n"
            "      alert add --kind percent_change --symbol NVDA threshold=0.08\n"
            "  - Ticker rule (specific crypto):\n"
            "      alert add --kind percent_change --symbol BTC --asset-type CRYPTO threshold=0.08\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    help_on_error(add_p)
    add_p.add_argument("--kind", required=True, metavar="KIND", help="Detector kind (e.g. percent_change)")
    add_p.add_argument("--symbol", metavar="SYMBOL", help="Ticker symbol (omit for a global rule)")
    add_p.add_argument("--asset-type", metavar="TYPE", dest="asset_type", help="Asset type: STOCK, CRYPTO, or CURRENCY (optional for ticker rules; limits scope for global rules)")
    add_p.add_argument("args", nargs="*", metavar="KEY=VALUE", help="Detector arguments as key=value pairs")
    add_p.set_defaults(func=_run_add)

    # edit
    edit_p = sub.add_parser(
        "edit",
        help="Mute, unmute, enable, disable, or manage exclusions for a rule",
        description=(
            "Edit an alert rule.\n\n"
            "Examples:\n"
            "  alert edit <id> mute\n"
            "  alert edit <id> disable\n"
            "  alert edit <id> exclusions add BTC CRYPTO\n"
            "  alert edit <id> exclusions add NVDA           # STOCK is implicit\n"
            "  alert edit <id> exclusions remove BTC CRYPTO\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    help_on_error(edit_p)
    edit_p.add_argument("id", metavar="ID", help="Rule ID or unique prefix")
    edit_p.add_argument(
        "action",
        choices=["mute", "unmute", "enable", "disable", "exclusions"],
        metavar="ACTION",
        help="mute | unmute | enable | disable | exclusions",
    )
    edit_p.add_argument(
        "extra",
        nargs="*",
        metavar="...",
        help="For 'exclusions': add|remove <ticker> [asset_type]  (asset_type defaults to STOCK)",
    )
    edit_p.set_defaults(func=_run_edit)

    # remove
    rm_p = sub.add_parser("remove", help="Remove an alert rule by ID")
    help_on_error(rm_p)
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
        rules = [_rule_out(r).model_dump() for r in config.get("rules") or []]
        print(json.dumps(rules, indent=2))
        return

    rows = _alert_rows(config)
    if not rows:
        print("(no alert rules configured)")
    else:
        render_table(rows)


def _run_show(args: argparse.Namespace) -> None:
    client = make_client(args)
    rule = _resolve_rule(client, args.id)

    if args.json_out:
        out = _rule_out(rule).model_dump()
        exclusions = rule.get("excluded_tickers") or []
        out["excluded_tickers"] = exclusions
        print(json.dumps(out, indent=2))
        return

    _print_rule_detail(rule)


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

    asset_type: str | None = args.asset_type.strip().upper() if args.asset_type else None

    client = make_client(args)
    body: dict[str, Any] = {
        "ticker": args.symbol.upper() if args.symbol else "",
        "kind": args.kind,
        "args": detector_args,
    }
    if asset_type is not None:
        body["asset_type"] = asset_type

    resp = client.post(_RULES_ENDPOINT, json=body)
    if not resp.is_success:
        detail = resp.text.strip()
        print(f"error: {resp.status_code}" + (f": {detail}" if detail else ""), file=sys.stderr)
        sys.exit(1)

    rule = resp.json()
    if args.symbol:
        scope = f"symbol '{args.symbol.upper()}'"
    elif asset_type:
        scope = f"all {asset_type.lower()} assets"
    else:
        scope = "all assets"
    print(f"ok: added {args.kind} for {scope}  (id={rule['id'][:8]})")


def _run_edit(args: argparse.Namespace) -> None:
    client = make_client(args)
    rule = _resolve_rule(client, args.id)
    rule_id = rule["id"]

    action = args.action
    extra: list[str] = getattr(args, "extra", [])

    if action == "exclusions":
        if len(extra) < 2:
            print("error: usage: edit <id> exclusions add|remove <ticker> [asset_type]", file=sys.stderr)
            sys.exit(1)
        sub_action = extra[0].lower()
        if sub_action not in ("add", "remove"):
            print(f"error: exclusions sub-action must be 'add' or 'remove', got '{sub_action}'", file=sys.stderr)
            sys.exit(1)
        ex_ticker = extra[1].upper()
        ex_asset_type = extra[2].upper() if len(extra) >= 3 else "STOCK"
        excl_base = f"{_RULES_ENDPOINT}/{rule_id}/exclusions"

        if sub_action == "add":
            resp = client.post(excl_base, json={"ticker": ex_ticker, "asset_type": ex_asset_type})
        else:
            resp = client.delete(f"{excl_base}/{ex_asset_type}/{ex_ticker}")

        if not resp.is_success:
            detail = resp.text.strip()
            print(f"error: {resp.status_code}" + (f": {detail}" if detail else ""), file=sys.stderr)
            sys.exit(1)

        print(f"ok: {sub_action}d exclusion {ex_ticker} ({ex_asset_type}) for {rule.get('kind')} rule  (id={rule_id[:8]})")
        return

    if action == "mute":
        patch: dict[str, Any] = {"mute": True}
    elif action == "unmute":
        patch = {"mute": False}
    elif action == "enable":
        patch = {"enabled": True}
    else:  # disable
        patch = {"enabled": False}

    resp = client.put(f"{_RULES_ENDPOINT}/{rule_id}", json=patch)
    if not resp.is_success:
        detail = resp.text.strip()
        print(f"error: {resp.status_code}" + (f": {detail}" if detail else ""), file=sys.stderr)
        sys.exit(1)

    ticker = rule.get("ticker") or "(global)"
    print(f"ok: {action}d {rule.get('kind')} for {ticker}  (id={rule_id[:8]})")


def _run_remove(args: argparse.Namespace) -> None:
    client = make_client(args)
    rule = _resolve_rule(client, args.id)
    rule_id = rule["id"]

    resp = client.delete(f"{_RULES_ENDPOINT}/{rule_id}")
    if not resp.is_success:
        detail = resp.text.strip()
        print(f"error: {resp.status_code}" + (f": {detail}" if detail else ""), file=sys.stderr)
        sys.exit(1)

    ticker = rule.get("ticker") or "(global)"
    print(f"ok: removed {rule.get('kind')} for {ticker}  (id={rule_id[:8]})")


def _run_detectors(args: argparse.Namespace) -> None:
    client = make_client(args, require_token=False)
    detectors = client.get_json("/api/v1/detectors")

    if args.json_out:
        print(json.dumps(detectors, indent=2))
        return

    if not detectors:
        print("(no detectors registered)")
    else:
        _print_detectors(detectors)
