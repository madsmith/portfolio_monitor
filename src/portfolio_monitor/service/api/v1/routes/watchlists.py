import json

import logfire
from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.data import DataProvider
from portfolio_monitor.utils import logfire_set_attribute
from portfolio_monitor.service.context import AuthContext
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.watchlist.models import Watchlist, WatchlistEntry
from portfolio_monitor.watchlist.service import WatchlistService


def _entry_dict(entry: WatchlistEntry, current_price: float | None = None) -> dict:
    price = current_price
    return {
        "ticker": entry.symbol.ticker,
        "asset_type": entry.symbol.asset_type.value,
        "current_price": price,
        "notes": entry.notes,
        "target_buy": entry.target_buy,
        "target_sell": entry.target_sell,
        "time_added": entry.time_added.isoformat() if entry.time_added else None,
        "initial_price": entry.initial_price,
        "meta": entry.meta,
        "alerts": entry.alerts,
    }


def _watchlist_summary(wl: Watchlist) -> dict:
    return {
        "id": wl.id,
        "name": wl.name,
        "owner": wl.owner,
        "entry_count": len(wl.entries),
    }


def _watchlist_detail(wl: Watchlist) -> dict:
    return {
        "id": wl.id,
        "name": wl.name,
        "owner": wl.owner,
        "entries": [_entry_dict(e) for e in wl.entries],
    }


def watchlists_handler(watchlist_service: WatchlistService, data_provider: DataProvider):
    @logfire.instrument("api.watchlists.list")
    async def list_watchlists(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        return JSONResponse([_watchlist_summary(wl) for wl in watchlist_service.get_watchlists(auth)])

    @logfire.instrument("api.watchlists.create")
    async def create_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)
        owner = body.get("owner", auth.username) if auth.is_admin else auth.username
        wl = await watchlist_service.create_watchlist(name, owner)
        return JSONResponse(_watchlist_detail(wl), status_code=201)

    @logfire.instrument("api.watchlists.get")
    async def get_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl = watchlist_service.get_watchlist(request.path_params["id"], auth)
        logfire_set_attribute("watchlist_id", request.path_params["id"])
        if wl is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        # Always fetch the freshest available price via get_aggregate.
        # entry.current_price is a runtime field driven by the server-side Polygon WS
        # feed; it only updates while a client has that ticker subscribed, so it can
        # be arbitrarily stale.  get_aggregate returns the most recent bar from the
        # REST-backed aggregate cache (or falls back to entry.current_price if None).
        prices: dict[str, float] = {}
        with logfire.span("watchlist.get.prices", entry_count=len(wl.entries)):
            for entry in wl.entries:
                agg = await data_provider.get_aggregate(entry.symbol)
                if agg is not None:
                    prices[entry.symbol.ticker] = agg.close
                elif entry.current_price is not None:
                    prices[entry.symbol.ticker] = float(entry.current_price._value)
            logfire_set_attribute("fetched_count", len(prices))
        entries = [_entry_dict(e, prices.get(e.symbol.ticker)) for e in wl.entries]
        return JSONResponse({"id": wl.id, "name": wl.name, "owner": wl.owner, "entries": entries})

    @logfire.instrument("api.watchlists.delete")
    async def delete_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        deleted = await watchlist_service.delete_watchlist(request.path_params["id"], auth)
        if not deleted:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse({"ok": True})

    @logfire.instrument("api.watchlists.entry.add")
    async def add_entry(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl_id = request.path_params["id"]
        body = await request.json()
        ticker = body.get("ticker", "").strip().upper()
        if not ticker:
            return JSONResponse({"error": "ticker is required"}, status_code=400)
        raw_type = body.get("asset_type", "stock")
        try:
            asset_type = AssetTypes(raw_type)
        except ValueError:
            return JSONResponse({"error": f"invalid asset_type: {raw_type}"}, status_code=400)
        initial_price: float | None = float(body["initial_price"]) if body.get("initial_price") is not None else None
        entry = WatchlistEntry(
            symbol=AssetSymbol(ticker, asset_type),
            notes=str(body.get("notes") or ""),
            target_buy=float(body["target_buy"]) if body.get("target_buy") is not None else None,
            target_sell=float(body["target_sell"]) if body.get("target_sell") is not None else None,
            initial_price=initial_price,
            meta=dict(body.get("meta") or {}),
            alerts=dict(body.get("alerts") or {}),
        )
        if entry.initial_price is None:
            agg = await data_provider.get_aggregate(entry.symbol)
            if agg is not None:
                entry.initial_price = float(agg.close)
        wl = await watchlist_service.add_entry(wl_id, entry, auth)
        if wl is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_watchlist_detail(wl))

    @logfire.instrument("api.watchlists.entry.remove")
    async def remove_entry(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl = await watchlist_service.remove_entry(
            request.path_params["id"],
            request.path_params["ticker"].upper(),
            auth,
        )
        if wl is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_watchlist_detail(wl))

    @logfire.instrument("api.watchlists.entry.update")
    async def update_entry(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        body = await request.json()
        _UNSET = object()
        target_buy = (float(body["target_buy"]) if body["target_buy"] is not None else None) if "target_buy" in body else _UNSET
        target_sell = (float(body["target_sell"]) if body["target_sell"] is not None else None) if "target_sell" in body else _UNSET
        wl = await watchlist_service.update_entry_fields(
            request.path_params["id"],
            request.path_params["ticker"].upper(),
            notes=body.get("notes"),
            target_buy=target_buy,   # type: ignore[arg-type]
            target_sell=target_sell, # type: ignore[arg-type]
            meta_patch=body.get("meta"),
            auth=auth,
        )
        if wl is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_watchlist_detail(wl))

    @logfire.instrument("api.watchlists.entry.alerts.get")
    async def get_entry_alerts(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl = watchlist_service.get_watchlist(request.path_params["id"], auth)
        if wl is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        entry = wl.get_entry(request.path_params["ticker"].upper())
        if entry is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        return JSONResponse(entry.alerts)

    @logfire.instrument("api.watchlists.entry.alerts.update")
    async def update_entry_alerts(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        alerts = await request.json()
        if not isinstance(alerts, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        wl = await watchlist_service.update_entry_alerts(
            request.path_params["id"],
            request.path_params["ticker"].upper(),
            alerts,
            auth,
        )
        if wl is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        entry = wl.get_entry(request.path_params["ticker"].upper())
        return JSONResponse(entry.alerts if entry else {})

    return (
        list_watchlists,
        create_watchlist,
        get_watchlist,
        delete_watchlist,
        add_entry,
        remove_entry,
        update_entry,
        get_entry_alerts,
        update_entry_alerts,
    )
