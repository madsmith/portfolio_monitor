import asyncio
import logging
import signal

import uvicorn

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import MemoryOnlyAggregateCache
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.loader import load_portfolios
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts import (
    AlertRouter,
    LoggingAlertDelivery,
    OpenClawAgentHttpDelivery,
)
from portfolio_monitor.service.api.app import create_api_app
from portfolio_monitor.service.types import AssetSymbol

from .config import SEED_PRICES, DevConfig
from .data_provider import DevDataProvider
from .synthetic_source import SyntheticDataSource

logger = logging.getLogger(__name__)


async def run_dev_service(config: DevConfig) -> None:
    """Run the monitor service in dev mode with synthetic data."""

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 1. Load portfolios (same as production)
    portfolios = load_portfolios(config.portfolio_path)

    if config.debug:
        print("=== Dev Mode ===")
        print(f"Tick interval: {config.tick_interval}s")
        for portfolio in portfolios:
            print(portfolio)
        print("================")

    # 2. Memory-only aggregate cache
    aggregate_cache = MemoryOnlyAggregateCache()

    # 3. EventBus + cache persistence
    bus = EventBus()

    async def _persist_aggregate(event: AggregateUpdated) -> None:
        await aggregate_cache.add(event.aggregate)

    bus.subscribe(AggregateUpdated, _persist_aggregate)

    # 4. Detection engine (same build logic as production)
    monitors_config = config.monitors
    default_detectors_config = monitors_config.get("default") or {}
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
    detection_engine = DeviationEngine(default_detectors=default_detectors)

    # Per-asset detectors
    all_symbols: list[AssetSymbol] = list(
        {asset.symbol for portfolio in portfolios for asset in portfolio.assets()}
    )
    symbol_lookup: dict[str, AssetSymbol] = {s.ticker: s for s in all_symbols}

    for ticker, detector_configs in monitors_config.items():
        if ticker == "default":
            continue
        if not detector_configs:
            continue
        symbol = symbol_lookup.get(ticker)
        if symbol is None:
            logger.warning(
                "Ticker %s from monitors config not found in portfolios", ticker
            )
            continue
        for name, args in detector_configs.items():
            detection_engine.add_detector(symbol, {"name": name, "args": args})

    # 5. SyntheticDataSource
    synthetic_source = SyntheticDataSource(
        bus=bus,
        symbols=all_symbols,
        seed_prices=SEED_PRICES,
        tick_interval=config.tick_interval,
    )

    # 6. DevDataProvider (mirrors DataProvider API without Polygon)
    dev_data_provider = DevDataProvider(
        aggregate_cache=aggregate_cache,
        price_generator=synthetic_source.generator,
        symbols=all_symbols,
    )

    # 7. Services (identical to production)
    detection_service = DetectionService(
        bus=bus,
        detection_engine=detection_engine,
        data_provider=dev_data_provider,
    )
    portfolio_service = PortfolioService(bus=bus, portfolios=portfolios)  # noqa: F841
    alert_router = AlertRouter(bus=bus)
    # Suppress all alert delivery by default in dev mode;
    # detectors still process data and build history.
    alert_router.suppressed_detectors = {
        d.name for d in detection_engine.default_detectors
    } | {
        d.name
        for detectors in detection_engine.asset_detectors.values()
        for d in detectors
    }
    alert_router.add_target(LoggingAlertDelivery())
    # TODO: make configurable or state driven.
    alert_router.add_target(
        OpenClawAgentHttpDelivery(
            config.openclaw_host,
            config.openclaw_port,
            config.openclaw_auth_key,
            config.openclaw_agent_id,
            name="Portfolio Alert",
            session_key=config.openclaw_session_key,
        )
    )

    # 8. Prime with synthetic history
    logger.info(
        "Priming detection engine with %d minutes of synthetic history...",
        config.prime_history_minutes,
    )
    history = synthetic_source.generate_history(config.prime_history_minutes)
    for agg in history:
        await aggregate_cache.add(agg)
        detection_engine.detect(agg)
    detection_engine.clear_cooldowns()
    logger.info("Detection engine primed (%d aggregates)", len(history))

    # 9. Control panel
    from .control_panel.app import ControlPanelApp

    control_panel = ControlPanelApp(
        bus=bus,
        synthetic_source=synthetic_source,
        detection_engine=detection_engine,
        detection_service=detection_service,
        alert_router=alert_router,
        aggregate_cache=aggregate_cache,
        portfolios=portfolios,
    )

    # 10. Production API server (auth workflow, dashboard, API endpoints)
    api_app = create_api_app(
        config.auth_key, config.dashboard_username, config.dashboard_password
    )

    # 11. Start both servers
    dev_uvicorn_config = uvicorn.Config(
        control_panel.app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    dev_server = uvicorn.Server(dev_uvicorn_config)

    api_uvicorn_config = uvicorn.Config(
        api_app,
        host=config.host,
        port=config.api_port,
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

    try:
        await alert_router.connect_all()
        await synthetic_source.start()
        print(f"\nControl:   http://{config.host}:{config.port}/")
        print(f"Dashboard: http://{config.host}:{config.api_port}/")
        print(f"API:       http://{config.host}:{config.api_port}/api/v1/health")
        print(f"Login:     {config.dashboard_username} / {config.dashboard_password}")
        print(f"Auth key:  {config.auth_key[:8]}...{config.auth_key[-4:]}\n")
        await asyncio.gather(dev_server.serve(), api_server.serve())
    except asyncio.CancelledError:
        logger.info("Dev mode cancelled, shutting down...")
    except Exception:
        logger.exception("Error in dev service")
        raise
    finally:
        await synthetic_source.stop()
        await alert_router.disconnect_all()
        loop.remove_signal_handler(signal.SIGINT)
        signal.signal(signal.SIGINT, original_handler)
