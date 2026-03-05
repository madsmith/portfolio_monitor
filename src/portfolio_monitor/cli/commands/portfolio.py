import argparse
import sys

import httpx

_SECTION_TO_TYPE = {"stocks": "stock", "currencies": "currency", "crypto": "crypto"}


def add_portfolio_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("portfolio", help="Query portfolio data")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="List all portfolios")
    group.add_argument("--id", metavar="ID", help="Show details for a specific portfolio")
    p.set_defaults(func=run_portfolio)


def run_portfolio(args: argparse.Namespace) -> None:
    if not args.token:
        print("error: --token is required for portfolio commands", file=sys.stderr)
        sys.exit(1)

    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.url.rstrip("/")

    if args.all:
        _list_all(base, headers)
    else:
        _get_one(base, headers, args.id)


def _get(url: str, headers: dict) -> dict | list:
    try:
        response = httpx.get(url, headers=headers)
    except httpx.ConnectError:
        print(f"error: could not connect to {url}", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 401:
        print("error: unauthorized — check your token", file=sys.stderr)
        sys.exit(1)
    if response.status_code == 404:
        print("error: portfolio not found", file=sys.stderr)
        sys.exit(1)
    if response.status_code != 200:
        print(f"error: server returned {response.status_code}", file=sys.stderr)
        sys.exit(1)

    return response.json()


def _fetch_prev_close(base: str, headers: dict, asset_type: str, ticker: str) -> float | None:
    try:
        r = httpx.get(
            f"{base}/api/v1/price/{asset_type}/{ticker}/previous-close",
            headers=headers,
        )
        if r.status_code == 200:
            return r.json().get("price")
    except httpx.ConnectError:
        pass
    return None


def _fmt_num(value: float | None, prefix: str = "$") -> str:
    if value is None:
        return "—"
    return f"{prefix}{value:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_change(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:,.2f}"


def _list_all(base: str, headers: dict) -> None:
    portfolios = _get(f"{base}/api/v1/portfolios", headers)
    assert isinstance(portfolios, list)

    if not portfolios:
        print("No portfolios found.")
        return

    rows = []
    for p in portfolios:
        detail = _get(f"{base}/api/v1/portfolio/{p['id']}", headers)
        assert isinstance(detail, dict)

        day_change = 0.0
        prev_total = 0.0
        has_data = False
        for section, asset_type in _SECTION_TO_TYPE.items():
            for a in detail.get(section, []):
                prev = _fetch_prev_close(base, headers, asset_type, a["ticker"])
                cur = a["current_price"]
                if prev is not None and cur is not None:
                    qty = float(a["total_quantity"])
                    day_change += qty * (cur - prev)
                    prev_total += qty * prev
                    has_data = True

        day_val = day_change if has_data else None
        day_pct = (day_change / prev_total * 100) if (has_data and prev_total) else None

        rows.append((
            p["id"],
            p["name"],
            _fmt_num(p["total_value"]),
            _fmt_change(day_val),
            _fmt_pct(day_pct),
            _fmt_num(p["total_profit_loss"]),
            _fmt_pct(p["profit_loss_percentage"]),
        ))

    col_id    = max(len("ID"),    max(len(r[0]) for r in rows)) + 2
    col_name  = max(len("Name"),  max(len(r[1]) for r in rows)) + 2
    col_value = max(len("Value"), max(len(r[2]) for r in rows)) + 2
    col_dval  = max(len("Day $"), max(len(r[3]) for r in rows)) + 2
    col_dpct  = max(len("Day %"), max(len(r[4]) for r in rows)) + 2
    col_pl    = max(len("P&L"),   max(len(r[5]) for r in rows)) + 2
    col_pct   = max(len("P&L %"), max(len(r[6]) for r in rows)) + 2

    header = (
        f"{'ID':<{col_id}}"
        f"{'Name':<{col_name}}"
        f"{'Value':>{col_value}}"
        f"{'Day $':>{col_dval}}"
        f"{'Day %':>{col_dpct}}"
        f"{'P&L':>{col_pl}}"
        f"{'P&L %':>{col_pct}}"
    )
    print(header)
    print("-" * len(header))

    for r in rows:
        print(
            f"{r[0]:<{col_id}}"
            f"{r[1]:<{col_name}}"
            f"{r[2]:>{col_value}}"
            f"{r[3]:>{col_dval}}"
            f"{r[4]:>{col_dpct}}"
            f"{r[5]:>{col_pl}}"
            f"{r[6]:>{col_pct}}"
        )


def _get_one(base: str, headers: dict, portfolio_id: str) -> None:
    p = _get(f"{base}/api/v1/portfolio/{portfolio_id}", headers)
    assert isinstance(p, dict)

    print(f"Portfolio: {p['name']}  (id: {p['id']})")
    print(
        f"Value: {_fmt_num(p['total_value'])}  "
        f"Cost basis: {_fmt_num(p['total_cost_basis'])}  "
        f"P&L: {_fmt_num(p['total_profit_loss'])}  "
        f"({_fmt_pct(p['profit_loss_percentage'])})"
    )

    for section in ("stocks", "currencies", "crypto"):
        assets = p.get(section, [])
        if not assets:
            continue

        asset_type = _SECTION_TO_TYPE[section]

        rows = []
        for a in assets:
            prev = _fetch_prev_close(base, headers, asset_type, a["ticker"])
            cur = a["current_price"]
            qty = float(a["total_quantity"])

            day_pct: float | None = None
            day_val: float | None = None
            if prev is not None and cur is not None:
                day_pct = (cur - prev) / prev * 100
                day_val = qty * (cur - prev)

            rows.append((
                a["ticker"],
                a["total_quantity"],
                _fmt_num(cur),
                _fmt_pct(day_pct),
                _fmt_num(a["current_value"]),
                _fmt_change(day_val),
                _fmt_num(a["profit_loss"]),
                _fmt_pct(a["profit_loss_percentage"]),
            ))

        col_ticker = max(len("Ticker"), max(len(r[0]) for r in rows)) + 2
        col_qty    = max(len("Qty"),    max(len(r[1]) for r in rows)) + 2
        col_price  = max(len("Price"),  max(len(r[2]) for r in rows)) + 2
        col_dpct   = max(len("Day %"),  max(len(r[3]) for r in rows)) + 2
        col_value  = max(len("Value"),  max(len(r[4]) for r in rows)) + 2
        col_dval   = max(len("Day $"),  max(len(r[5]) for r in rows)) + 2
        col_pl     = max(len("P&L"),    max(len(r[6]) for r in rows)) + 2
        col_pct    = max(len("P&L %"),  max(len(r[7]) for r in rows)) + 2

        header = (
            f"  {'Ticker':<{col_ticker}}  "
            f"{'Qty':>{col_qty}}  "
            f"{'Price':>{col_price}}  "
            f"{'Day %':>{col_dpct}}  "
            f"{'Value':>{col_value}}  "
            f"{'Day $':>{col_dval}}  "
            f"{'P&L':>{col_pl}}  "
            f"{'P&L %':>{col_pct}}"
        )
        print(f"\n{section.capitalize()}:")
        print(header)
        print("  " + "-" * (len(header) - 2))

        for r in rows:
            print(
                f"  {r[0]:<{col_ticker}}  "
                f"{r[1]:>{col_qty}}  "
                f"{r[2]:>{col_price}}  "
                f"{r[3]:>{col_dpct}}  "
                f"{r[4]:>{col_value}}  "
                f"{r[5]:>{col_dval}}  "
                f"{r[6]:>{col_pl}}  "
                f"{r[7]:>{col_pct}}"
            )
