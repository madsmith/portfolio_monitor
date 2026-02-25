import asyncio
import logging
import signal
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import MemoryOnlyAggregateCache
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.loader import load_portfolios
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts import AlertRouter, LoggingAlertDelivery
from portfolio_monitor.service.types import AssetSymbol

from .config import SEED_PRICES, DevConfig
from .synthetic_source import SyntheticDataSource

logger = logging.getLogger(__name__)


async def run_dev_service(config: DevConfig) -> None:
    """Run the monitor service in dev mode with synthetic data."""

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 1. Load portfolios (same as production)
    portfolios = load_portfolios(config.portfolio_path)

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
        logger.info("No detectors in config — using all %d registered detectors", len(default_detectors))
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
            logger.warning("Ticker %s from monitors config not found in portfolios", ticker)
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

    # 6. Services (identical to production)
    detection_service = DetectionService(  # noqa: F841
        bus=bus,
        detection_engine=detection_engine,
    )
    portfolio_service = PortfolioService(bus=bus, portfolios=portfolios)  # noqa: F841
    alert_router = AlertRouter(bus=bus)
    alert_router.add_target(LoggingAlertDelivery())

    # 7. Prime with synthetic history
    logger.info("Priming detection engine with %d minutes of synthetic history...", config.prime_history_minutes)
    history = synthetic_source.generate_history(config.prime_history_minutes)
    for agg in history:
        await aggregate_cache.add(agg)
        detection_engine.detect(agg)
    detection_engine.clear_cooldowns()
    logger.info("Detection engine primed (%d aggregates)", len(history))

    # 8. Dev UI
    from .dev_ui.app import DevUIApp

    dev_ui = DevUIApp(
        bus=bus,
        synthetic_source=synthetic_source,
        detection_engine=detection_engine,
        aggregate_cache=aggregate_cache,
        portfolios=portfolios,
    )

    # 9. Start
    uvicorn_config = uvicorn.Config(
        dev_ui.app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    api_server = uvicorn.Server(uvicorn_config)

    # Stop synthetic source immediately on SIGINT so alerts don't keep
    # firing while uvicorn drains connections.
    loop = asyncio.get_running_loop()
    original_handler = signal.getsignal(signal.SIGINT)

    def _initiate_shutdown():
        logger.info("Shutdown initiated — stopping synthetic source")
        dev_ui.shutdown()
        loop.create_task(synthetic_source.stop())
        api_server.should_exit = True

    dev_ui._stop_callback = _initiate_shutdown
    loop.add_signal_handler(signal.SIGINT, _initiate_shutdown)

    try:
        await alert_router.connect_all()
        await synthetic_source.start()
        print(f"\nDev UI: http://{config.host}:{config.port}/\n")
        await api_server.serve()
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
