import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.service.context import AuthContext
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.watchlist.models import Watchlist, WatchlistEntry
from portfolio_monitor.watchlist.service import WatchlistService


def _entry_dict(entry: WatchlistEntry, fallback_price: float | None = None) -> dict:
    price = float(entry.current_price._value) if entry.current_price is not None else fallback_price
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
    async def list_watchlists(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        return JSONResponse([_watchlist_summary(wl) for wl in watchlist_service.get_watchlists(auth)])

    async def create_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            return JSONResponse({"error": "name is required"}, status_code=400)
        owner = body.get("owner", auth.username) if auth.is_admin else auth.username
        wl = await watchlist_service.create_watchlist(name, owner)
        return JSONResponse(_watchlist_detail(wl), status_code=201)

    async def get_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl = watchlist_service.get_watchlist(request.path_params["id"], auth)
        if wl is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        # For entries with no live price (e.g. market closed, new entry), fall back
        # to get_aggregate which returns previous close when the market is closed.
        fallbacks: dict[str, float] = {}
        for entry in wl.entries:
            if entry.current_price is None:
                agg = await data_provider.get_aggregate(entry.symbol)
                if agg is not None:
                    fallbacks[entry.symbol.ticker] = agg.close
        entries = [_entry_dict(e, fallbacks.get(e.symbol.ticker)) for e in wl.entries]
        return JSONResponse({"id": wl.id, "name": wl.name, "owner": wl.owner, "entries": entries})

    async def delete_watchlist(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        deleted = await watchlist_service.delete_watchlist(request.path_params["id"], auth)
        if not deleted:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse({"ok": True})

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
        entry = WatchlistEntry(
            symbol=AssetSymbol(ticker, asset_type),
            notes=str(body.get("notes") or ""),
            target_buy=float(body["target_buy"]) if body.get("target_buy") is not None else None,
            target_sell=float(body["target_sell"]) if body.get("target_sell") is not None else None,
            meta=dict(body.get("meta") or {}),
            alerts=dict(body.get("alerts") or {}),
        )
        wl = await watchlist_service.add_entry(wl_id, entry, auth)
        if wl is None:
            return JSONResponse({"error": "not found or forbidden"}, status_code=404)
        return JSONResponse(_watchlist_detail(wl))

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

    async def update_entry(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        body = await request.json()
        _UNSET = object()
        target_buy = float(body["target_buy"]) if "target_buy" in body else _UNSET
        target_sell = float(body["target_sell"]) if "target_sell" in body else _UNSET
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

    async def get_entry_alerts(request: Request) -> JSONResponse:
        auth = AuthContext.from_request(request)
        wl = watchlist_service.get_watchlist(request.path_params["id"], auth)
        if wl is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        entry = wl.get_entry(request.path_params["ticker"].upper())
        if entry is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        return JSONResponse(entry.alerts)

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
