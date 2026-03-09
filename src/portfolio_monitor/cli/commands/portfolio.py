import argparse
import json
import sys
from typing import Annotated

import httpx
from pydantic import BaseModel

from portfolio_monitor.cli.display import ColumnMeta, fmt_value, model_to_dict, render_table

_SECTION_TO_TYPE = {"stocks": "stock", "currencies": "currency", "crypto": "crypto"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PortfolioSummaryRow(BaseModel):
    id:                Annotated[str,          ColumnMeta("ID")]
    name:              Annotated[str,          ColumnMeta("Name")]
    total_value:       Annotated[float | None, ColumnMeta("Value", fmt="currency")]
    day_change:        Annotated[float | None, ColumnMeta("Day $", fmt="change")]
    day_change_pct:    Annotated[float | None, ColumnMeta("Day %", fmt="percent")]
    total_profit_loss: Annotated[float | None, ColumnMeta("P&L", fmt="change")]
    profit_loss_pct:   Annotated[float | None, ColumnMeta("P&L %", fmt="percent")]
    # Included in JSON but not rendered as a table column
    total_cost_basis:  Annotated[float | None, ColumnMeta("Cost Basis", fmt="currency", json_only=True)]


class AssetRow(BaseModel):
    ticker:            Annotated[str,          ColumnMeta("Ticker", min_width=10)]
    total_quantity:    Annotated[str,          ColumnMeta("Qty", fmt="right")]
    current_price:     Annotated[float | None, ColumnMeta("Price", fmt="currency")]
    day_change_pct:    Annotated[float | None, ColumnMeta("Day %", fmt="percent")]
    current_value:     Annotated[float | None, ColumnMeta("Value", fmt="currency")]
    day_change:        Annotated[float | None, ColumnMeta("Day $", fmt="change")]
    profit_loss:       Annotated[float | None, ColumnMeta("P&L", fmt="change")]
    profit_loss_pct:   Annotated[float | None, ColumnMeta("P&L %", fmt="percent")]
    # JSON-only — present in model_dump() but not rendered in the table
    asset_type:        Annotated[str,          ColumnMeta("Type", json_only=True)]
    cost_basis:        Annotated[float | None, ColumnMeta("Cost Basis", fmt="currency", json_only=True)]
    lots:              Annotated[list[dict],   ColumnMeta("Lots", json_only=True)]


class PortfolioHeader(BaseModel):
    id: str
    name: str
    total_value: float | None
    total_cost_basis: float | None
    total_profit_loss: float | None
    profit_loss_pct: float | None


class PortfolioDetailOutput(BaseModel):
    header: PortfolioHeader
    stocks: list[AssetRow] = []
    currencies: list[AssetRow] = []
    crypto: list[AssetRow] = []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_portfolio_detail(output: PortfolioDetailOutput) -> None:
    h = output.header
    print(f"Portfolio: {h.name}  (id: {h.id})")
    print(
        f"Value: {fmt_value(h.total_value, 'currency')}  "
        f"Cost basis: {fmt_value(h.total_cost_basis, 'currency')}  "
        f"P&L: {fmt_value(h.total_profit_loss, 'change')}  "
        f"({fmt_value(h.profit_loss_pct, 'percent')})"
    )

    for label, assets in [("Stocks", output.stocks), ("Currencies", output.currencies), ("Crypto", output.crypto)]:
        if not assets:
            continue
        print(f"\n{label}:")
        render_table(assets, indent="  ")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def add_portfolio_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("portfolio", help="Query portfolio data")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="List all portfolios")
    group.add_argument("--id", metavar="ID", help="Show details for a specific portfolio")
    p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    p.set_defaults(func=run_portfolio)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def run_portfolio(args: argparse.Namespace) -> None:
    if not args.token:
        print("error: --token is required for portfolio commands", file=sys.stderr)
        sys.exit(1)

    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.url.rstrip("/")

    if args.all:
        _list_all(base, headers, args.json_out)
    else:
        _get_one(base, headers, args.id, args.json_out)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

def _build_summary_rows(base: str, headers: dict, portfolios: list) -> list[PortfolioSummaryRow]:
    rows: list[PortfolioSummaryRow] = []
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

        day_val: float | None = day_change if has_data else None
        day_pct: float | None = (day_change / prev_total * 100) if (has_data and prev_total) else None

        rows.append(PortfolioSummaryRow(
            id=p["id"],
            name=p["name"],
            total_value=p["total_value"],
            day_change=day_val,
            day_change_pct=day_pct,
            total_profit_loss=p["total_profit_loss"],
            profit_loss_pct=p["profit_loss_percentage"],
            total_cost_basis=p["total_cost_basis"],
        ))
    return rows


def _build_asset_rows(base: str, headers: dict, assets: list, asset_type: str) -> list[AssetRow]:
    rows: list[AssetRow] = []
    for a in assets:
        prev = _fetch_prev_close(base, headers, asset_type, a["ticker"])
        cur = a["current_price"]
        qty = float(a["total_quantity"])

        day_pct: float | None = None
        day_val: float | None = None
        if prev is not None and cur is not None:
            day_pct = (cur - prev) / prev * 100
            day_val = qty * (cur - prev)

        rows.append(AssetRow(
            ticker=a["ticker"],
            total_quantity=a["total_quantity"],
            current_price=cur,
            day_change_pct=day_pct,
            current_value=a["current_value"],
            day_change=day_val,
            profit_loss=a["profit_loss"],
            profit_loss_pct=a["profit_loss_percentage"],
            asset_type=a["asset_type"],
            cost_basis=a["cost_basis"],
            lots=a["lots"],
        ))
    return rows


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _list_all(base: str, headers: dict, json_out: bool = False) -> None:
    portfolios = _get(f"{base}/api/v1/portfolios", headers)
    assert isinstance(portfolios, list)

    rows = _build_summary_rows(base, headers, portfolios)

    if json_out:
        print(json.dumps([model_to_dict(r) for r in rows], indent=2))
        return

    if not rows:
        print("No portfolios found.")
        return

    render_table(rows)


def _get_one(base: str, headers: dict, portfolio_id: str, json_out: bool = False) -> None:
    p = _get(f"{base}/api/v1/portfolio/{portfolio_id}", headers)
    assert isinstance(p, dict)

    header = PortfolioHeader(
        id=p["id"],
        name=p["name"],
        total_value=p["total_value"],
        total_cost_basis=p["total_cost_basis"],
        total_profit_loss=p["total_profit_loss"],
        profit_loss_pct=p["profit_loss_percentage"],
    )
    stocks = _build_asset_rows(base, headers, p.get("stocks", []), "stock")
    currencies = _build_asset_rows(base, headers, p.get("currencies", []), "currency")
    crypto = _build_asset_rows(base, headers, p.get("crypto", []), "crypto")
    output = PortfolioDetailOutput(header=header, stocks=stocks, currencies=currencies, crypto=crypto)

    if json_out:
        result = {
            "header": output.header.model_dump(),
            "stocks": [model_to_dict(r) for r in output.stocks],
            "currencies": [model_to_dict(r) for r in output.currencies],
            "crypto": [model_to_dict(r) for r in output.crypto],
        }
        print(json.dumps(result, indent=2))
        return

    render_portfolio_detail(output)
