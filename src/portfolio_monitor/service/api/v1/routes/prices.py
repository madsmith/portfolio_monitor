from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.service.types import AssetSymbol, AssetTypes


def _parse_symbol(request: Request) -> AssetSymbol | None:
    type_str = request.path_params["type"]
    ticker = request.path_params["ticker"]
    try:
        asset_type = AssetTypes(type_str)
    except ValueError:
        return None
    return AssetSymbol(ticker=ticker, asset_type=asset_type)


def _agg_response(symbol: AssetSymbol, aggregate) -> dict:
    return {
        "symbol": symbol.to_dict(),
        "price": aggregate.close,
        "timestamp": aggregate.date_open.isoformat(),
    }


def current_price_handler(data_provider: DataProvider):
    async def get_current_price(request: Request) -> JSONResponse:
        symbol = _parse_symbol(request)
        if symbol is None:
            return JSONResponse({"error": "invalid asset type"}, status_code=400)
        aggregate = await data_provider.get_aggregate(symbol)
        if aggregate is None:
            return JSONResponse({"error": "price unavailable"}, status_code=404)
        return JSONResponse(_agg_response(symbol, aggregate))

    return get_current_price


def previous_close_handler(data_provider: DataProvider):
    async def get_previous_close(request: Request) -> JSONResponse:
        symbol = _parse_symbol(request)
        if symbol is None:
            return JSONResponse({"error": "invalid asset type"}, status_code=400)
        aggregate = await data_provider.get_previous_close(symbol)
        if aggregate is None:
            return JSONResponse({"error": "price unavailable"}, status_code=404)
        return JSONResponse(_agg_response(symbol, aggregate))

    return get_previous_close
