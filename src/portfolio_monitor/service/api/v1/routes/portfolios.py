import asyncio
import logfire
from datetime import datetime, timedelta, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core import Currency
from portfolio_monitor.data import DataProvider
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


def _asset_dict(asset: Asset, price_override: float | None = None) -> dict:
    indexed = list(enumerate(asset.lots))
    sorted_indexed = sorted(indexed, key=lambda x: (x[1].date is None, x[1].date), reverse=True)
    if price_override is not None:
        current_price: float | None = price_override
        qty = float(asset.total_quantity)
        current_value: float | None = price_override * qty
        cost = float(asset.cost_basis._value) if asset.cost_basis is not None else None
        profit_loss: float | None = (current_value - cost) if cost is not None else None
        pl_pct: float | None = (profit_loss / cost * 100) if cost is not None and cost != 0 else None
    else:
        current_price = _currency_val(asset.current_price)
        current_value = _currency_val(asset.current_value)
        profit_loss = _currency_val(asset.profit_loss)
        raw_pct = asset.profit_loss_percentage
        pl_pct = float(raw_pct) if raw_pct is not None else None
    return {
        "ticker": asset.symbol.ticker,
        "asset_type": asset.asset_type,
        "total_quantity": str(asset.total_quantity),
        "cost_basis": _currency_val(asset.cost_basis),
        "current_price": current_price,
        "current_value": current_value,
        "profit_loss": profit_loss,
        "profit_loss_percentage": pl_pct,
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


def _portfolio_detail(p: Portfolio, prices: dict[str, float] | None = None) -> dict:
    def asset(a: Asset) -> dict:
        return _asset_dict(a, prices.get(a.symbol.ticker) if prices else None)
    all_assets = [asset(a) for a in [*p.stocks, *p.currencies, *p.crypto]]
    if prices:
        total_value = sum(a["current_value"] for a in all_assets if a["current_value"] is not None)
        total_cost = float(p.total_cost_basis._value) if p.total_cost_basis is not None else None
        total_pl = (total_value - total_cost) if total_cost is not None else None
        pl_pct = (total_pl / total_cost * 100) if total_cost is not None and total_cost != 0 else None
    else:
        raw_pct = p.profit_loss_percentage
        total_value = _currency_val(p.total_value)  # type: ignore[assignment]
        total_cost = _currency_val(p.total_cost_basis)  # type: ignore[assignment]
        total_pl = _currency_val(p.total_profit_loss)  # type: ignore[assignment]
        pl_pct = float(raw_pct) if raw_pct is not None else None
    stocks = [a for a in all_assets if a["asset_type"] == "stock"]
    currencies = [a for a in all_assets if a["asset_type"] == "currency"]
    crypto = [a for a in all_assets if a["asset_type"] == "crypto"]
    return {
        "id": p.id,
        "name": p.name,
        "owner": p.owner,
        "total_value": total_value,
        "total_cost_basis": total_cost,
        "total_profit_loss": total_pl,
        "profit_loss_percentage": pl_pct,
        "stocks": stocks,
        "currencies": currencies,
        "crypto": crypto,
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


def create_portfolio_handler(portfolio_service: PortfolioService):
    async def create_portfolio(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        body = await request.json()
        name = (body.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)
        portfolio = portfolio_service.create_portfolio(name, auth)
        return JSONResponse(_portfolio_summary(portfolio), status_code=201)

    return create_portfolio


def delete_portfolio_handler(portfolio_service: PortfolioService):
    async def delete_portfolio(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        if not portfolio_service.delete_portfolio(portfolio_id, auth):
            return JSONResponse({"error": "not found or unauthorized"}, status_code=404)
        return JSONResponse({"ok": True})

    return delete_portfolio


def portfolio_handler(portfolio_service: PortfolioService, data_provider: DataProvider):
    @logfire.instrument("api.portfolios.get")
    async def get_portfolio(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        portfolio_id = request.path_params["id"]
        logfire_set_attribute("portfolio_id", portfolio_id)
        logfire_set_attribute("username", auth.username)
        portfolio = portfolio_service.get_portfolio(portfolio_id, auth)
        if portfolio is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        assets = list(portfolio.assets())
        with logfire.span("portfolio.get.prices", asset_count=len(assets)):
            aggs = await asyncio.gather(*[data_provider.get_aggregate(a.symbol) for a in assets])
        prices: dict[str, float] = {
            a.symbol.ticker: float(agg.close)
            for a, agg in zip(assets, aggs)
            if agg is not None
        }
        logfire_set_attribute("fetched_count", len(prices))
        return JSONResponse(_portfolio_detail(portfolio, prices))

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
        now = datetime.now(timezone.utc)
        if request.query_params.get("all") == "true":
            from_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
        else:
            try:
                days = min(int(request.query_params.get("days", 30)), 365)
            except (ValueError, TypeError):
                days = 30
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
