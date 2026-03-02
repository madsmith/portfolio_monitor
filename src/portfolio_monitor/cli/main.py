import argparse

from portfolio_monitor.cli.commands.login import add_login_parser


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

    return parser

def main() -> None:
    parser = get_arg_parser()

    args = parser.parse_args()
    
    args.func(args)


if __name__ == "__main__":
    main()
