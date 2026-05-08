import logfire
from datetime import datetime, timedelta, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core import Currency
from portfolio_monitor.data.database.performance import PortfolioPerformanceModule
from portfolio_monitor.utils import logfire_set_attribute
from portfolio_monitor.portfolio import Asset, Lot, Portfolio
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.context import AuthContext


def _currency_val(c: Currency | None) -> float | None:
    return float(c._value) if c is not None else None


def _lot_dict(lot: Lot, lot_idx: int | None = None) -> dict:
    d: dict = {
        "date": lot.date.isoformat() if lot.date is not None else None,
        "quantity": str(lot.quantity),
        "price": _currency_val(lot.price),
        "cost_basis": _currency_val(lot.cost_basis()),
        "fees": _currency_val(lot.fees),
        "rebates": _currency_val(lot.rebates),
    }
    if lot_idx is not None:
        d["lot_idx"] = lot_idx
    return d


def _asset_dict(asset: Asset) -> dict:
    pl_pct = asset.profit_loss_percentage
    indexed = list(enumerate(asset.lots))
    sorted_indexed = sorted(indexed, key=lambda x: (x[1].date is None, x[1].date), reverse=True)
    return {
        "ticker": asset.symbol.ticker,
        "asset_type": asset.asset_type,
        "total_quantity": str(asset.total_quantity),
        "cost_basis": _currency_val(asset.cost_basis),
        "current_price": _currency_val(asset.current_price),
        "current_value": _currency_val(asset.current_value),
        "profit_loss": _currency_val(asset.profit_loss),
        "profit_loss_percentage": float(pl_pct) if pl_pct is not None else None,
        "lots": [_lot_dict(lot, idx) for idx, lot in sorted_indexed],
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
        "owner": p.owner,
        "stocks": [_asset_dict(a) for a in p.stocks],
        "currencies": [_asset_dict(a) for a in p.currencies],
        "crypto": [_asset_dict(a) for a in p.crypto],
    }


def portfolios_handler(portfolio_service: PortfolioService):
    @logfire.instrument("api.portfolios.list")
    async def list_portfolios(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        logfire_set_attribute("username", auth.username)
        portfolios = portfolio_service.get_portfolios(auth)
        logfire_set_attribute("portfolio_count", len(portfolios))
        return JSONResponse([_portfolio_summary(p) for p in portfolios])

    return list_portfolios


def portfolio_handler(portfolio_service: PortfolioService):
    @logfire.instrument("api.portfolios.get")
    async def get_portfolio(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        logfire_set_attribute("portfolio_id", portfolio_id)
        logfire_set_attribute("username", auth.username)
        portfolio = portfolio_service.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(_portfolio_detail(portfolio))

    return get_portfolio


def portfolio_edit_handlers(portfolio_service: PortfolioService):
    async def add_lot(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        asset_type = request.path_params["asset_type"]
        ticker = request.path_params["ticker"].upper()
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid body"}, status_code=400)
        result = portfolio_service.add_lot(portfolio_id, asset_type, ticker, body, auth)
        if result is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        portfolio, _ = result
        return JSONResponse(_portfolio_detail(portfolio))

    async def update_lot(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        asset_type = request.path_params["asset_type"]
        ticker = request.path_params["ticker"].upper()
        lot_idx = int(request.path_params["lot_idx"])
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid body"}, status_code=400)
        result = portfolio_service.update_lot(portfolio_id, asset_type, ticker, lot_idx, body, auth)
        if result is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        portfolio, _ = result
        return JSONResponse(_portfolio_detail(portfolio))

    async def delete_lot(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        asset_type = request.path_params["asset_type"]
        ticker = request.path_params["ticker"].upper()
        lot_idx = int(request.path_params["lot_idx"])
        result = portfolio_service.delete_lot(portfolio_id, asset_type, ticker, lot_idx, auth)
        if result is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_portfolio_detail(result))

    async def delete_asset_handler(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        asset_type = request.path_params["asset_type"]
        ticker = request.path_params["ticker"].upper()
        result = portfolio_service.delete_asset(portfolio_id, asset_type, ticker, auth)
        if result is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_portfolio_detail(result))

    return add_lot, update_lot, delete_lot, delete_asset_handler


def portfolio_performance_handler(
    portfolio_service: PortfolioService,
    performance_module: PortfolioPerformanceModule,
):
    async def get_portfolio_performance(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        portfolio = portfolio_service.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            days = min(int(request.query_params.get("days", 30)), 365)
        except (ValueError, TypeError):
            days = 30
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(days=days)
        snapshots = performance_module.get_range(portfolio_id, from_dt, now)
        return JSONResponse({"portfolio_id": portfolio_id, "snapshots": snapshots})

    return get_portfolio_performance


def portfolio_users_handler(portfolio_service: PortfolioService):
    async def get_portfolio_users(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        portfolio = portfolio_service.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({
            "owner": portfolio.owner,
            "permissions": portfolio.permissions.to_dict() if portfolio.permissions else {},
        })

    async def update_portfolio_users(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid body"}, status_code=400)
        permissions: dict = body.get("permissions", {})
        portfolio = portfolio_service.update_permissions(portfolio_id, permissions, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=403)
        return JSONResponse({"ok": True})

    return get_portfolio_users, update_portfolio_users
