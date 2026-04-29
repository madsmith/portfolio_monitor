from datetime import datetime
from zoneinfo import ZoneInfo

from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core import parse_date
from portfolio_monitor.data import MarketInfo, MarketStatus
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_UTC = ZoneInfo("UTC")


def _parse_symbol(request: Request) -> AssetSymbol | None:
    type_str = request.path_params["type"]
    ticker = request.path_params["ticker"]
    try:
        asset_type = AssetTypes(type_str)
    except ValueError:
        return None
    return AssetSymbol(ticker=ticker, asset_type=asset_type)


def _parse_time(request: Request) -> datetime | None | str:
    """Return the resolved reference datetime, None for 'now', or 'error'."""
    time_str = request.query_params.get("time")
    if not time_str:
        return None
    dt = parse_date(time_str)
    if dt is None:
        return "error"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt


def _status_str(symbol: AssetSymbol, at_time: datetime) -> str:
    return MarketInfo.get_market_status(symbol, at_time).value


def market_hours_handler(request: Request) -> JSONResponse:
    symbol = _parse_symbol(request)
    if symbol is None:
        return JSONResponse({"error": "invalid asset type"}, status_code=400)

    at_time = _parse_time(request)
    if at_time == "error":
        return JSONResponse({"error": "invalid time parameter"}, status_code=400)
    if at_time is None:
        at_time = datetime.now(_UTC)

    hours = MarketInfo.get_market_hours(symbol, at_time)
    return JSONResponse({
        "symbol": symbol.to_dict(),
        "status": _status_str(symbol, at_time),
        "hours": {status.value: dt.isoformat() for status, dt in hours.items()},
    })


def market_close_handler(request: Request) -> JSONResponse:
    symbol = _parse_symbol(request)
    if symbol is None:
        return JSONResponse({"error": "invalid asset type"}, status_code=400)

    at_time = _parse_time(request)
    if at_time == "error":
        return JSONResponse({"error": "invalid time parameter"}, status_code=400)
    if at_time is None:
        at_time = datetime.now(_UTC)

    close = MarketInfo.get_market_close(symbol, at_time)
    return JSONResponse({
        "symbol": symbol.to_dict(),
        "status": _status_str(symbol, at_time),
        "close": close.isoformat(),
    })


def market_open_handler(request: Request) -> JSONResponse:
    symbol = _parse_symbol(request)
    if symbol is None:
        return JSONResponse({"error": "invalid asset type"}, status_code=400)

    at_time = _parse_time(request)
    if at_time == "error":
        return JSONResponse({"error": "invalid time parameter"}, status_code=400)
    if at_time is None:
        at_time = datetime.now(_UTC)

    open_ = MarketInfo.get_market_open(symbol, at_time)
    return JSONResponse({
        "symbol": symbol.to_dict(),
        "status": _status_str(symbol, at_time),
        "open": open_.isoformat(),
    })
