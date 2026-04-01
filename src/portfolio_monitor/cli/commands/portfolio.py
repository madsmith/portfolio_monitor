import argparse
import json
import sys
from typing import Annotated

from pydantic import BaseModel

from portfolio_monitor.cli.request import APIClient, make_client
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
    p.add_argument("--json", dest="json_out", action="store_true", help="Output raw JSON instead of formatted text")
    sub = p.add_subparsers(dest="portfolio_command", metavar="SUBCOMMAND")
    sub.required = True

    # list
    sub.add_parser("list", help="List all portfolios")

    # show
    s = sub.add_parser("show", help="Show details for a specific portfolio")
    s.add_argument("id", metavar="ID")

    p.set_defaults(func=run_portfolio)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def run_portfolio(args: argparse.Namespace) -> None:
    client = make_client(args)
    if args.portfolio_command == "list":
        _list_all(client, args.json_out)
    else:
        _show_one(client, args.id, args.json_out)


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

def _build_summary_rows(client: APIClient, portfolios: list) -> list[PortfolioSummaryRow]:
    rows: list[PortfolioSummaryRow] = []
    for p in portfolios:
        detail = client.get_json(f"/api/v1/portfolio/{p['id']}")
        assert isinstance(detail, dict)

        day_change = 0.0
        prev_total = 0.0
        has_data = False
        for section, asset_type in _SECTION_TO_TYPE.items():
            for a in detail.get(section, []):
                data = client.get_json(f"/api/v1/price/{asset_type}/{a['ticker']}/previous-close")
                prev = data.get("price") if data else None
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


def _build_asset_rows(client: APIClient, assets: list, asset_type: str) -> list[AssetRow]:
    rows: list[AssetRow] = []
    for asset in assets:
        data = client.get_json(f"/api/v1/price/{asset_type}/{asset['ticker']}/previous-close")
        prev = data.get("price") if data else None
        cur = asset["current_price"]
        qty = float(asset["total_quantity"])

        day_pct: float | None = None
        day_val: float | None = None
        if prev is not None and cur is not None:
            day_pct = (cur - prev) / prev * 100
            day_val = qty * (cur - prev)

        rows.append(AssetRow(
            ticker=asset["ticker"],
            total_quantity=asset["total_quantity"],
            current_price=cur,
            day_change_pct=day_pct,
            current_value=asset["current_value"],
            day_change=day_val,
            profit_loss=asset["profit_loss"],
            profit_loss_pct=asset["profit_loss_percentage"],
            asset_type=asset["asset_type"],
            cost_basis=asset["cost_basis"],
            lots=asset["lots"],
        ))
    return rows


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _list_all(client: APIClient, json_out: bool = False) -> None:
    portfolios = client.get_json("/api/v1/portfolios")
    assert isinstance(portfolios, list)

    rows = _build_summary_rows(client, portfolios)

    if json_out:
        print(json.dumps([model_to_dict(r) for r in rows], indent=2))
        return

    if not rows:
        print("No portfolios found.")
        return

    render_table(rows)


def _show_one(client: APIClient, portfolio_id: str, json_out: bool = False) -> None:
    portfolio = client.get_json(f"/api/v1/portfolio/{portfolio_id}")
    assert isinstance(portfolio, dict)

    header = PortfolioHeader(
        id=portfolio["id"],
        name=portfolio["name"],
        total_value=portfolio["total_value"],
        total_cost_basis=portfolio["total_cost_basis"],
        total_profit_loss=portfolio["total_profit_loss"],
        profit_loss_pct=portfolio["profit_loss_percentage"],
    )
    stocks = _build_asset_rows(client, portfolio.get("stocks", []), "stock")
    currencies = _build_asset_rows(client, portfolio.get("currencies", []), "currency")
    crypto = _build_asset_rows(client, portfolio.get("crypto", []), "crypto")
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
