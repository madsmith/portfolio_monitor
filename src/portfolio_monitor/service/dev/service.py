import asyncio
import logging
import signal
from pathlib import Path

from appconf import OmegaConfigLoader
import uvicorn

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import AggregateUpdated, MemoryOnlyAggregateCache, PolygonDataProvider
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.watchlist.service import WatchlistService
from portfolio_monitor.service.alerts import (
    AlertBufferStore,
    ChannelPool,
    UserAlertManager,
)
from portfolio_monitor.service.api.app import create_api_app
from portfolio_monitor.service.context import PortfolioMonitorContext
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.account import AccountStore
from portfolio_monitor.session import SessionStore
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.service.vite import ViteProcess, start_vite

from portfolio_monitor.service.event_hooks import AlertConfigAdapter, WatchlistAdapter

from .config import DevConfig
from .data_provider import DevDataProvider
from .seed_price_provider import SeedPriceProvider
from .synthetic_source import SyntheticDataSource

logger = logging.getLogger(__name__)


async def run_dev_service(config: DevConfig) -> None:
    """Run the monitor service in dev mode with synthetic data."""

    # Initialize database
    db = AppDatabase(config.datastore_path)
    db.initialize()

    # 2. Memory-only aggregate cache
    aggregate_cache = MemoryOnlyAggregateCache()

    # 3. EventBus + cache persistence
    bus = EventBus()

    async def _persist_aggregate(event: AggregateUpdated) -> None:
        await aggregate_cache.add(event.aggregate)

    bus.subscribe(AggregateUpdated, _persist_aggregate)

    # Load portfolios
    portfolio_service = PortfolioService(bus=bus, db=db)
    portfolios = portfolio_service.get_all_portfolios()

    if config.debug:
        print("=== Dev Mode ===")
        print(f"Tick interval: {config.tick_interval}s")
        for portfolio in portfolios:
            print(portfolio)
        print("================")

    # 4. Detection engine (same build logic as production)
    try:
        alert_config = OmegaConfigLoader.load(Path("config/alerts_dev.yaml"))
    except Exception:
        alert_config = {}

    default_detectors_config = alert_config.get("default") or {}
    if default_detectors_config:
        default_detectors = [
            {"name": name, "args": args}
            for name, args in default_detectors_config.items()
        ]
    else:
        # No detectors configured — use all registered with default args
        from portfolio_monitor.detectors import DetectorRegistry

        default_detectors = [
            {"name": name, "args": {}}
            for name in DetectorRegistry.list_available_detectors()
        ]
        logger.info(
            "No detectors in config — using all %d registered detectors",
            len(default_detectors),
        )
    detection_engine = DeviationEngine(
        default_detectors=default_detectors,
    )

    # Per-asset detectors
    all_symbols: list[AssetSymbol] = list(
        {asset.symbol for portfolio in portfolios for asset in portfolio.assets()}
    )
    symbol_lookup: dict[str, AssetSymbol] = {s.ticker: s for s in all_symbols}

    for key, value in alert_config.items():
        if type(key) is not str:
            continue
        if key == "default":
            continue
        if isinstance(value, dict):
            ticker = key.upper()
            symbol = symbol_lookup.get(ticker)
            if symbol is None:
                logger.warning(
                    "Ticker %s from monitors config not found in portfolios", ticker
                )
                continue
            for name, args in value.items():
                detection_engine.add_detector(symbol, {"name": name, "args": args})
    
    seed_price_provider = SeedPriceProvider(
        portfolios=portfolios,
        data_provider=PolygonDataProvider(config=config, aggregate_cache=aggregate_cache),
    )
    await seed_price_provider.load()
    seed_aggregates = seed_price_provider.get_aggregates()
    synthetic_source = SyntheticDataSource(
        bus=bus,
        symbols=all_symbols,
        seed_price_provider=seed_price_provider,
        tick_interval=config.tick_interval,
    )

    # 6. DevDataProvider (mirrors DataProvider API without Polygon)
    dev_data_provider = DevDataProvider(
        aggregate_cache=aggregate_cache,
        price_generator=synthetic_source.generator,
        symbols=all_symbols,
        seed_aggregates=seed_aggregates,
    )

    # 7. Services (identical to production)
    detection_service = DetectionService(
        bus=bus,
        detection_engine=detection_engine,
        data_provider=dev_data_provider,
    )
    account_store = AccountStore(db)
    alert_buffer_store = AlertBufferStore(db.alerts, bus)
    channel_pool = ChannelPool()
    alert_manager = UserAlertManager(
        bus=bus,
        alert_buffer_store=alert_buffer_store,
        alerts_module=db.alerts,
        channel_pool=channel_pool,
    )
    # TODO(openclaw): openclaw delivery will be a channel type in the DB config
    # alert_manager.add_target(LoggingAlertDelivery())

    # 8. Prime with synthetic history starting from the seed point (previous close).
    # Seed aggregates go into the cache first so get_previous_close() has a real
    # timestamp to anchor to. Then synthetic minute bars fill in from that point
    # to now, giving detectors a continuous price history.
    for agg in seed_aggregates.values():
        await aggregate_cache.add(agg)

    if seed_aggregates:
        seed_start = min(agg.date_open for agg in seed_aggregates.values())
        logger.info(
            "Priming detection engine from seed point %s to now...",
            seed_start.isoformat(),
        )
        history = synthetic_source.generate_history(start=seed_start)
    else:
        logger.info(
            "No seed aggregates available; priming with %d minutes of synthetic history",
            config.prime_history_minutes,
        )
        history = synthetic_source.generate_history(config.prime_history_minutes)

    last_per_symbol = {}
    for agg in history:
        await aggregate_cache.add(agg)
        detection_engine.detect(agg)
        last_per_symbol[agg.symbol] = agg
    detection_engine.reset_state()
    logger.info("Detection engine primed (%d aggregates)", len(history))

    # Seed portfolio prices with the most recent primed aggregate per symbol
    for agg in last_per_symbol.values():
        await bus.publish(AggregateUpdated(symbol=agg.symbol, aggregate=agg))

    # 9. Control panel
    from .control_panel.app import ControlPanelApp

    control_panel = ControlPanelApp(
        bus=bus,
        synthetic_source=synthetic_source,
        detection_engine=detection_engine,
        detection_service=detection_service,
        alert_manager=alert_manager,
        aggregate_cache=aggregate_cache,
        portfolios=portfolios,
    )

    # 10. Production API server (auth workflow, dashboard, API endpoints)
    session_store = SessionStore(db, config.dashboard_username or "default")
    watchlist_service = WatchlistService(bus=bus, db=db)
    monitor_service = MonitorService(bus=bus, data_provider=dev_data_provider, portfolio_service=portfolio_service)
    for wl in watchlist_service.get_all_watchlists():
        for entry in wl.entries:
            monitor_service.register_symbol(entry.symbol)
    WatchlistAdapter(detection_engine, alert_manager, monitor_service, detection_service, dev_data_provider, alert_adapter=alert_adapter).wire(bus)
    alert_adapter = AlertConfigAdapter(
        engine=detection_engine,
        alert_manager=alert_manager,
        detection_service=detection_service,
        portfolio_service=portfolio_service,
        watchlist_service=watchlist_service,
        alerts_module=db.alerts,
    )
    alert_adapter.wire(bus)
    alert_adapter.load_all()

    alert_manager.suppressed_detectors = {
        detector.name()
        for detector in detection_engine.default_detectors
    } | {
        detector.name()
        for detectors in detection_engine.asset_detectors.values()
        for detector in detectors
    }

    ctx = PortfolioMonitorContext(
        config=config,
        db=db,
        portfolio_service=portfolio_service,
        watchlist_service=watchlist_service,
        bus=bus,
        data_provider=dev_data_provider,
        account_store=account_store,
        session_store=session_store,
        alert_buffer_store=alert_buffer_store,
    )
    api_app = create_api_app(ctx)

    # 11. Start both servers
    dev_uvicorn_config = uvicorn.Config(
        control_panel.app,
        host=config.host,
        port=config.control_panel_port,
        log_level="debug" if config.debug else "info",
    )
    dev_server = uvicorn.Server(dev_uvicorn_config)

    api_uvicorn_config = uvicorn.Config(
        api_app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    api_server = uvicorn.Server(api_uvicorn_config)

    # Stop synthetic source immediately on SIGINT so alerts don't keep
    # firing while uvicorn drains connections.
    loop = asyncio.get_running_loop()
    original_handler = signal.getsignal(signal.SIGINT)

    def _initiate_shutdown():
        logger.info("Shutdown initiated — stopping synthetic source")
        control_panel.shutdown()
        loop.create_task(synthetic_source.stop())
        dev_server.should_exit = True
        api_server.should_exit = True

    control_panel._stop_callback = _initiate_shutdown
    loop.add_signal_handler(signal.SIGINT, _initiate_shutdown)

    vite: ViteProcess | None = None
    try:
        await alert_manager.connect_all()
        await synthetic_source.start()
        serve_task = asyncio.gather(dev_server.serve(), api_server.serve())
        while not api_server.started:
            await asyncio.sleep(0.05)
        frontend_dir = Path(__file__).resolve().parents[4] / "frontend"
        vite = await start_vite(frontend_dir)
        print(f"\nControl:   http://{config.host}:{config.control_panel_port}/")
        print(f"Dashboard: http://{config.host}:{config.port}/")
        print(f"Frontend:  {vite.url}")
        print(f"API:       http://{config.host}:{config.port}/api/v1/health")
        print(f"Login:     {config.dashboard_username} / {config.dashboard_password}")
        print(f"Auth key:  {config.auth_key[:8]}...{config.auth_key[-4:]}\n")
        await serve_task
    except asyncio.CancelledError:
        logger.info("Dev mode cancelled, shutting down...")
    except Exception:
        logger.exception("Error in dev service")
        raise
    finally:
        if vite is not None and vite.returncode is None:
            vite.terminate()
            await vite.wait()
        await synthetic_source.stop()
        await alert_manager.disconnect_all()
        loop.remove_signal_handler(signal.SIGINT)
        signal.signal(signal.SIGINT, original_handler)
