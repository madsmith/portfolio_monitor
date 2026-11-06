"""Shared ``share`` subcommands for permissioned resources (watchlists, portfolios).

Subcommands (mounted under ``watchlist share`` and ``portfolio share``):
  show   ID                  Show owner and per-user read/write access
  add    ID USER [--write]   Grant USER read access (read+write with --write)
  remove ID USER             Revoke USER's access
  clear  ID                  Remove all sharing (owner only)

The API's PUT replaces the whole permissions map, so add/remove fetch the
current map, modify it, and send it back.
"""

import argparse
import json
import sys
from typing import Annotated

from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, render_table
from portfolio_monitor.cli.request import APIClient
from portfolio_monitor.cli.utils import help_on_error


class ShareRow(BaseModel):
    username: Annotated[str,  ColumnMeta("User")]
    read:     Annotated[bool, ColumnMeta("Read")]
    write:    Annotated[bool, ColumnMeta("Write")]


def add_share_parser(
    sub: argparse._SubParsersAction,
    *,
    resource: str,
    id_metavar: str,
    json_parent: argparse.ArgumentParser,
) -> None:
    """Attach a ``share`` subcommand group to a resource's subparsers."""
    p = sub.add_parser("share", help=f"Show or change who can access a {resource}", parents=[json_parent])
    help_on_error(p)
    share_sub = p.add_subparsers(dest="share_command", metavar="SUBCOMMAND")
    share_sub.required = True

    s = share_sub.add_parser("show", help="Show owner and per-user access", parents=[json_parent])
    help_on_error(s)
    s.add_argument("id", metavar=id_metavar)

    s = share_sub.add_parser("add", help="Grant a user read (or read+write) access", parents=[json_parent])
    help_on_error(s)
    s.add_argument("id", metavar=id_metavar)
    s.add_argument("username", metavar="USER", help="Username (see `account list`)")
    s.add_argument("--write", action="store_true", help="Also grant write access")

    s = share_sub.add_parser("remove", help="Revoke a user's access", parents=[json_parent])
    help_on_error(s)
    s.add_argument("id", metavar=id_metavar)
    s.add_argument("username", metavar="USER")

    s = share_sub.add_parser(
        "clear",
        help="Remove all explicit sharing (owner only)",
        parents=[json_parent],
    )
    help_on_error(s)
    s.add_argument("id", metavar=id_metavar)


def run_share(client: APIClient, args: argparse.Namespace, *, base_path: str, resource: str) -> None:
    """Dispatch a ``share`` subcommand. ``base_path`` is e.g. ``/api/v1/watchlist``."""
    path = f"{base_path}/{args.id}/users"
    cmd = args.share_command

    if cmd == "show":
        _print_share(client.get_json(path), args.json_out)
        return

    current = client.get_json(path)
    owner: str = current["owner"]
    perms: dict[str, dict[str, bool]] = dict(current.get("permissions") or {})

    if cmd == "add":
        user = args.username
        if user == owner:
            _fail(f"{user} owns this {resource} and already has full access")
        known = {u["username"] for u in client.get_json("/api/v1/users")}
        if user not in known:
            _fail(f"unknown user '{user}' (see `portfolio-manager account list`)")
        perms[user] = {"read": True, "write": bool(args.write)}

    elif cmd == "remove":
        user = args.username
        if user not in perms:
            _fail(f"{user} has no explicit access to this {resource}")
        del perms[user]

    elif cmd == "clear":
        perms = {}

    else:
        _fail(f"unknown share subcommand: {cmd}")

    resp = client.put(path, json={"permissions": perms})
    if not resp.is_success:
        _fail(f"server returned {resp.status_code}: {resp.text}")
    _print_share(client.get_json(path), args.json_out)


def _print_share(data: dict, json_out: bool) -> None:
    if json_out:
        print(json.dumps(data, indent=2))
        return
    owner = data["owner"]
    perms = data.get("permissions") or {}
    print(f"Owner: {owner}")
    if not perms:
        print("  (not shared — owner only)")
        return
    rows = [ShareRow(username=u, read=p.get("read", False), write=p.get("write", False)) for u, p in perms.items()]
    render_table(rows, indent="  ")


def _fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)
