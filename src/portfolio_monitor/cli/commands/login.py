import argparse
import sys

import httpx


def add_login_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("login", help="Authenticate and obtain a bearer token")
    p.add_argument("--username", required=True, metavar="USERNAME", help="Dashboard username")
    p.add_argument("--password", required=True, metavar="PASSWORD", help="Dashboard password")
    p.set_defaults(func=run_login)


def run_login(args: argparse.Namespace) -> None:
    url = f"{args.url.rstrip('/')}/api/v1/login"
    try:
        response = httpx.post(url, json={"username": args.username, "password": args.password})
    except httpx.ConnectError:
        print(f"error: could not connect to {args.url}", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 200:
        print(response.json()["token"])
    elif response.status_code == 401:
        print("error: invalid credentials", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)
