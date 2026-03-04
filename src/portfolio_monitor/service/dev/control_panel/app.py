import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import AggregateCache
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors.engine import DeviationEngine
from portfolio_monitor.detectors.events import AlertFired
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.portfolio import Portfolio
from portfolio_monitor.service.alerts.router import AlertRouter
from portfolio_monitor.service.dev.price_generator import Regime
from portfolio_monitor.service.dev.synthetic_source import SyntheticDataSource  # noqa: TC001

logger = logging.getLogger(__name__)

DIST_DIR = Path(__file__).resolve().parents[5] / "frontend" / "dist"


class ControlPanelApp:
    """Unauthenticated dev control panel with SSE for real-time updates."""

    def __init__(
        self,
        bus: EventBus,
        synthetic_source: SyntheticDataSource | None,
        detection_engine: DeviationEngine,
        detection_service: DetectionService,
        alert_router: AlertRouter,
        aggregate_cache: AggregateCache,
        portfolios: list[Portfolio],
    ) -> None:
        self._bus: EventBus = bus
        self._source: SyntheticDataSource | None = synthetic_source
        self._engine: DeviationEngine = detection_engine
        self._detection_service: DetectionService = detection_service
        self._alert_router: AlertRouter = alert_router
        self._cache: AggregateCache = aggregate_cache
        self._portfolios: list[Portfolio] = portfolios

        # SSE subscriber queues
        self._alert_queues: list[asyncio.Queue] = []
        self._price_queues: list[asyncio.Queue] = []
        self._shutdown: asyncio.Event = asyncio.Event()
        self._stop_callback: Callable[[], None] | None = None

        # Subscribe to events for SSE broadcast
        self._bus.subscribe(AlertFired, self._on_alert_for_sse)
        self._bus.subscribe(AggregateUpdated, self._on_price_for_sse)

        self.app: Starlette = Starlette(
            routes=[
                Route("/api/state", self.get_state, methods=["GET"]),
                Route("/api/bias", self.set_bias, methods=["POST"]),
                Route("/api/pause", self.toggle_pause, methods=["POST"]),
                Route("/api/regime", self.set_regime, methods=["POST"]),
                Route("/api/tick-interval", self.set_tick_interval, methods=["POST"]),
                Route(
                    "/api/detector/{name}/toggle",
                    self.toggle_detector,
                    methods=["POST"],
                ),
                Route("/api/reset", self.reset, methods=["POST"]),
                Route("/api/clear-alerts", self.clear_alerts, methods=["POST"]),
                Route("/api/stop", self.stop_server, methods=["POST"]),
                Route("/sse/alerts", self.sse_alerts, methods=["GET"]),
                Route("/sse/prices", self.sse_prices, methods=["GET"]),
                Route("/sse/tick-progress", self.sse_tick_progress, methods=["GET"]),
                # Catch-all: serve built SPA or not-built fallback
                Route("/{path:path}", self.serve_spa, methods=["GET"]),
            ],
        )

    def shutdown(self) -> None:
        """Signal all SSE streams to stop."""
        self._shutdown.set()

    # ------------------------------------------------------------------
    # SPA serving
    # ------------------------------------------------------------------

    async def serve_spa(self, request: Request) -> Response:
        path = request.path_params.get("path", "")
        if path:
            file = DIST_DIR / path
            if file.is_file():
                return FileResponse(file)
        html = DIST_DIR / "control-panel.html"
        if html.is_file():
            return FileResponse(html)
        return HTMLResponse(
            "<h1>Frontend not built</h1>"
            "<p>Run: <code>cd frontend &amp;&amp; pnpm install &amp;&amp; pnpm build</code></p>",
            status_code=503,
        )

    # ------------------------------------------------------------------
    # API endpoints
    # ------------------------------------------------------------------

    async def get_state(self, request: Request) -> JSONResponse:
        all_symbols = list(
            {asset.symbol for p in self._portfolios for asset in p.assets()}
        )
        symbols_data = []
        for symbol in sorted(all_symbols, key=lambda s: s.ticker):
            if self._source is not None:
                price = self._source.generator.get_price(symbol.ticker)
            else:
                agg = self._cache.get_current(symbol)
                price = agg.close if agg is not None else None
            symbols_data.append(
                {
                    "ticker": symbol.ticker,
                    "asset_type": symbol.asset_type.value,
                    "price": price,
                }
            )

        detector_names = [d.name for d in self._engine.default_detectors]
        for detectors in self._engine.asset_detectors.values():
            for d in detectors:
                if d.name not in detector_names:
                    detector_names.append(d.name)

        return JSONResponse(
            {
                "synthetic": self._source is not None,
                "symbols": symbols_data,
                "detectors": detector_names,
                "suppressed_detectors": list(self._alert_router.suppressed_detectors),
                "tick_interval": self._source.tick_interval if self._source is not None else None,
                "paused": self._source.paused if self._source is not None else False,
            }
        )

    async def set_bias(self, request: Request) -> JSONResponse:
        if self._source is None:
            return JSONResponse({"ok": False, "error": "not available in live mode"}, status_code=405)
        body = await request.json()
        ticker = body["ticker"]
        bias_pct = float(body["bias_pct"])
        self._source.set_bias(ticker, bias_pct)
        return JSONResponse({"ok": True, "ticker": ticker, "bias_pct": bias_pct})

    async def toggle_pause(self, request: Request) -> JSONResponse:
        if self._source is None:
            return JSONResponse({"ok": False, "error": "not available in live mode"}, status_code=405)
        if self._source.paused:
            self._source.resume()
        else:
            self._source.pause()
        return JSONResponse({"ok": True, "paused": self._source.paused})

    async def set_regime(self, request: Request) -> JSONResponse:
        if self._source is None:
            return JSONResponse({"ok": False, "error": "not available in live mode"}, status_code=405)
        body = await request.json()
        regime = Regime(body["regime"].lower())
        self._source.set_regime(regime)
        return JSONResponse({"ok": True, "regime": regime.value})

    async def set_tick_interval(self, request: Request) -> JSONResponse:
        if self._source is None:
            return JSONResponse({"ok": False, "error": "not available in live mode"}, status_code=405)
        body = await request.json()
        interval = float(body["interval"])
        self._source.tick_interval = interval
        return JSONResponse({"ok": True, "tick_interval": self._source.tick_interval})

    async def toggle_detector(self, request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if name in self._alert_router.suppressed_detectors:
            self._alert_router.suppressed_detectors.discard(name)
            enabled = True
        else:
            self._alert_router.suppressed_detectors.add(name)
            enabled = False
        return JSONResponse({"ok": True, "detector": name, "enabled": enabled})

    async def reset(self, request: Request) -> JSONResponse:
        """Clear detector state and cooldowns, re-prime with fresh history."""
        if self._source is None:
            return JSONResponse({"ok": False, "error": "not available in live mode"}, status_code=405)
        # Clear cooldowns
        self._engine.clear_cooldowns()

        # Clear detector internal state (duck-type check for histories)
        for detector in self._engine.default_detectors:
            if hasattr(detector, "histories"):
                detector.histories.clear()  # type: ignore
            if hasattr(detector, "previous_closes"):
                detector.previous_closes.clear()  # type: ignore
            if hasattr(detector, "price_histories"):
                detector.price_histories.clear()  # type: ignore
            if hasattr(detector, "_price_history"):
                detector._price_history.clear()  # type: ignore

        # Re-prime
        history = self._source.generate_history(120)
        for agg in history:
            await self._cache.add(agg)
            self._engine.detect(agg)
        self._engine.clear_cooldowns()

        return JSONResponse({"ok": True, "primed_aggregates": len(history)})

    async def clear_alerts(self, request: Request) -> JSONResponse:
        """Clear the alert log in DetectionService."""
        self._detection_service.clear_alerts()
        return JSONResponse({"ok": True})

    async def stop_server(self, request: Request) -> JSONResponse:
        """Shut down the dev server."""
        if self._stop_callback:
            self._stop_callback()
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------
    # SSE endpoints
    # ------------------------------------------------------------------

    async def sse_alerts(self, request: Request) -> StreamingResponse:
        queue: asyncio.Queue = asyncio.Queue()
        self._alert_queues.append(queue)

        async def event_stream():
            try:
                while not self._shutdown.is_set():
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=1)
                        yield f"data: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                self._alert_queues.remove(queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def sse_prices(self, request: Request) -> StreamingResponse:
        queue: asyncio.Queue = asyncio.Queue()
        self._price_queues.append(queue)

        async def event_stream():
            try:
                while not self._shutdown.is_set():
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=1)
                        yield f"data: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                self._price_queues.remove(queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def sse_tick_progress(self, request: Request) -> StreamingResponse:
        async def event_stream():
            try:
                while not self._shutdown.is_set():
                    if await request.is_disconnected():
                        break
                    if self._source is not None:
                        data = {
                            "paused": self._source.paused,
                            "tick_interval": self._source.tick_interval,
                            "tick_count": self._source.tick_count,
                            "last_tick": (
                                self._source.last_tick_time.isoformat()
                                if self._source.last_tick_time
                                else None
                            ),
                            "next_tick": (
                                self._source.next_tick_time.isoformat()
                                if self._source.next_tick_time
                                else None
                            ),
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                    else:
                        yield ": keepalive\n\n"
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                pass

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # Event bus callbacks → SSE fan-out
    # ------------------------------------------------------------------

    async def _on_alert_for_sse(self, event: AlertFired) -> None:
        if event.alert.kind in self._alert_router.suppressed_detectors:
            return
        data = {
            "ticker": str(event.alert.ticker),
            "kind": event.alert.kind,
            "message": event.alert.message,
            "at": event.alert.at.isoformat(),
        }
        for queue in self._alert_queues:
            await queue.put(data)

    async def _on_price_for_sse(self, event: AggregateUpdated) -> None:
        data = {
            "ticker": str(event.symbol),
            "price": event.aggregate.close,
            "open": event.aggregate.open,
            "high": event.aggregate.high,
            "low": event.aggregate.low,
            "volume": event.aggregate.volume,
        }
        for queue in self._price_queues:
            await queue.put(data)
