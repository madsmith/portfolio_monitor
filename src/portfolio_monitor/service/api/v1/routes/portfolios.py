from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.portfolio.portfolio import Asset, Lot, Portfolio
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.context import AuthContext


def _currency_val(c: Currency | None) -> float | None:
    return float(c._value) if c is not None else None


def _lot_dict(lot: Lot) -> dict:
    return {
        "date": lot.date.isoformat() if lot.date is not None else None,
        "quantity": str(lot.quantity),
        "price": _currency_val(lot.price),
        "cost_basis": _currency_val(lot.cost_basis()),
        "fees": _currency_val(lot.fees),
        "rebates": _currency_val(lot.rebates),
    }


def _asset_dict(asset: Asset) -> dict:
    pl_pct = asset.profit_loss_percentage
    sorted_lots = sorted(
        asset.lots,
        key=lambda lot: (lot.date is None, lot.date),
        reverse=True,
    )
    return {
        "ticker": asset.symbol.ticker,
        "asset_type": asset.asset_type,
        "total_quantity": str(asset.total_quantity),
        "cost_basis": _currency_val(asset.cost_basis),
        "current_price": _currency_val(asset.current_price),
        "current_value": _currency_val(asset.current_value),
        "profit_loss": _currency_val(asset.profit_loss),
        "profit_loss_percentage": float(pl_pct) if pl_pct is not None else None,
        "lots": [_lot_dict(lot) for lot in sorted_lots],
    }


def _portfolio_summary(p: Portfolio) -> dict:
    pl_pct = p.profit_loss_percentage
    return {
        "id": p.id,
        "name": p.name,
        "total_value": _currency_val(p.total_value),
        "total_cost_basis": _currency_val(p.total_cost_basis),
        "total_profit_loss": _currency_val(p.total_profit_loss),
        "profit_loss_percentage": float(pl_pct) if pl_pct is not None else None,
    }


def _portfolio_detail(p: Portfolio) -> dict:
    return {
        **_portfolio_summary(p),
        "stocks": [_asset_dict(a) for a in p.stocks],
        "currencies": [_asset_dict(a) for a in p.currencies],
        "crypto": [_asset_dict(a) for a in p.crypto],
    }


def portfolios_handler(portfolio_service: PortfolioService):
    async def list_portfolios(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolios = portfolio_service.get_portfolios(auth)
        return JSONResponse([_portfolio_summary(p) for p in portfolios])

    return list_portfolios


def portfolio_handler(portfolio_service: PortfolioService):
    async def get_portfolio(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        portfolio = portfolio_service.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(_portfolio_detail(portfolio))

    return get_portfolio
