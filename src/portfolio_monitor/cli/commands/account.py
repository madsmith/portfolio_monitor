"""CLI commands for account management.

Subcommands:
  whoami    Show the current authenticated user
"""
import argparse

from portfolio_monitor.cli.request import make_client
from portfolio_monitor.cli.utils import help_on_error


def add_account_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("account", help="Account management")
    help_on_error(p)
    sub = p.add_subparsers(dest="account_subcommand", metavar="SUBCOMMAND")
    sub.required = True

    whoami_p = sub.add_parser("whoami", help="Show the current authenticated user")
    whoami_p.set_defaults(func=_run_whoami)


def _run_whoami(args: argparse.Namespace) -> None:
    client = make_client(args)
    me = client.get_json("/api/v1/me")
    print(f"{me['username']}  ({me['role']})")
