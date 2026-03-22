import argparse
import os

from portfolio_monitor.cli.commands.alerts import add_alerts_parser
from portfolio_monitor.cli.commands.login import add_login_parser
from portfolio_monitor.cli.commands.portfolio import add_portfolio_parser
from portfolio_monitor.cli.commands.prices import add_price_parser
from portfolio_monitor.cli.commands.watchlist import add_watchlist_parser


def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-manager",
        description="Nexus Portfolio Monitor CLI",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8400",
        metavar="URL",
        help="Base URL of the portfolio-monitor server API (default: http://127.0.0.1:8400)",
    )
    parser.add_argument(
        "--token",
        metavar="TOKEN",
        help="Bearer token for API authentication",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    add_login_parser(subparsers)
    add_portfolio_parser(subparsers)
    add_price_parser(subparsers)
    add_alerts_parser(subparsers)
    add_watchlist_parser(subparsers)

    return parser

def main() -> None:
    parser = get_arg_parser()

    args = parser.parse_args()

    if args.token is None:
        # Allow token to be passed via environment variable for convenience
        args.token = os.getenv("PORTFOLIO_MANAGER_TOKEN")

    args.func(args)


if __name__ == "__main__":
    main()
