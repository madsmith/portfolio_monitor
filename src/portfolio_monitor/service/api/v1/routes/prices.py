from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.core.datetime import parse_date, parse_period
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.data.market_info import MarketInfo, MarketStatus
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_MAX_HISTORY = timedelta(days=7)


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
            current_time = datetime.now()
            if MarketInfo.is_market_closed(symbol, current_time):
                # Fetch the last aggregate from the previous trading day (between close and after hours close)
                hours = MarketInfo.get_market_hours(symbol, current_time)

                aggregates = await data_provider.get_range(
                    symbol,
                    hours[MarketStatus.CLOSE],
                    hours[MarketStatus.AFTER_TRADING],
                )
                if aggregates:
                    return JSONResponse(_agg_response(symbol, aggregates[-1]))

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


def price_history_handler(data_provider: DataProvider):
    async def get_price_history(request: Request) -> JSONResponse:
        symbol = _parse_symbol(request)
        if symbol is None:
            return JSONResponse({"error": "invalid asset type"}, status_code=400)

        last_str = request.query_params.get("last")
        if not last_str:
            return JSONResponse({"error": "missing required parameter: last"}, status_code=400)
        try:
            delta = parse_period(last_str)
        except ValueError:
            return JSONResponse({"error": f"invalid period: {last_str!r}"}, status_code=400)

        if delta > _MAX_HISTORY:
            return JSONResponse({"error": "period exceeds maximum of 7 days"}, status_code=400)

        span_str = request.query_params.get("span")
        if span_str:
            try:
                span = AggregateTimespan.parse(span_str)
            except ValueError:
                return JSONResponse({"error": f"invalid span: {span_str!r}"}, status_code=400)
        else:
            span = AggregateTimespan.default()

        time_str = request.query_params.get("time")
        if time_str:
            to_time = parse_date(time_str)
            if to_time is None:
                return JSONResponse({"error": f"invalid time: {time_str!r}"}, status_code=400)
            if to_time.tzinfo is None:
                to_time = to_time.replace(tzinfo=ZoneInfo("UTC"))
        else:
            to_time = datetime.now(ZoneInfo("UTC"))

        from_time = to_time - delta
        aggregates = await data_provider.get_range(symbol, from_time, to_time, cache_write=True, span=span)

        if not aggregates:
            return JSONResponse({"error": "no data available"}, status_code=404)

        return JSONResponse({
            "symbol": symbol.to_dict(),
            "from": from_time.isoformat(),
            "to": to_time.isoformat(),
            "aggregates": [
                {
                    "timestamp": agg.date_open.isoformat(),
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": agg.volume,
                }
                for agg in aggregates
            ],
        })

    return get_price_history


def open_close_handler(data_provider: DataProvider):
    async def get_open_close(request: Request) -> JSONResponse:
        symbol = _parse_symbol(request)
        if symbol is None:
            return JSONResponse({"error": "invalid asset type"}, status_code=400)

        date_str = request.query_params.get("date")
        if date_str:
            date = parse_date(date_str)
            if date is None:
                return JSONResponse({"error": f"invalid date: {date_str!r}"}, status_code=400)
            if date.tzinfo is None:
                date = date.replace(tzinfo=ZoneInfo("UTC"))
        else:
            date = None

        result = await data_provider.get_open_close(symbol, date)
        if result is None:
            return JSONResponse({"error": "data unavailable"}, status_code=404)
        return JSONResponse(result.to_dict())

    return get_open_close
