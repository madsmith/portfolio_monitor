import argparse
import asyncio
import logging
import secrets
import sys

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

import logfire
import uvicorn
from appconf.omegaconf import OmegaConfig
from appconf.omegaconf.errors import PrivateConfigError
from omegaconf import OmegaConf
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from starlette.applications import Starlette
from uvicorn.server import Server

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import Aggregate, AggregateCache, AggregateUpdated, MarketInfo, PolygonDataProvider
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts import (
    ChannelPool,
    DashboardBufferDelivery,
    UserAlertManager,
)
from portfolio_monitor.service.event_hooks import AlertConfigAdapter, WatchlistAdapter
from portfolio_monitor.service.api import create_api_app
from portfolio_monitor.service.context import PortfolioMonitorContext
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.account import AccountStore
from portfolio_monitor.session import SessionStore
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.service.vite import ViteProcess, start_vite
from portfolio_monitor.utils.trace import TRACE
from portfolio_monitor.watchlist.service import WatchlistService



logger = logging.getLogger(__name__)


async def run_service(config: PortfolioMonitorConfig, *, is_live: bool = True, is_dev: bool = False) -> None:
    """Run the monitor service until interrupted"""

    # Initialize database
    db = AppDatabase(config.datastore_path)
    db.initialize()

    # Load aggregate cache
    with logfire.span("service.startup.cache_load"):
        aggregate_cache = AggregateCache(config.aggregate_cache_path)
        aggregate_cache.initialize()
        await aggregate_cache.load()

    with logfire.span("service.startup.wiring"):
        # Create event bus
        bus = EventBus()

        # Wire aggregate cache to persist on AggregateUpdated
        async def _persist_aggregate(event: AggregateUpdated) -> None:
            await aggregate_cache.add(event.aggregate)

        bus.subscribe(AggregateUpdated, _persist_aggregate)

        # Create data provider
        data_provider = PolygonDataProvider(config, aggregate_cache)

        # Initialize stores and services backed by AppDatabase
        account_store = AccountStore(db)
        session_store = SessionStore(db, config.dashboard_username or "default")

        portfolio_service = PortfolioService(bus=bus, db=db)
        watchlist_service = WatchlistService(bus=bus, db=db)

        detection_engine = DeviationEngine()

        # Create services — subscriptions happen in constructors
        detection_service = DetectionService(
            bus=bus,
            detection_engine=detection_engine,
            data_provider=data_provider,
        )
        channel_pool = ChannelPool()
        alert_manager = UserAlertManager(
            bus=bus,
            alerts_module=db.alerts,
            channel_pool=channel_pool,
        )
        alert_manager.add_implicit_delivery(DashboardBufferDelivery(db.alerts, bus))

        monitor = MonitorService(
            bus=bus,
            data_provider=data_provider,
            portfolio_service=portfolio_service,
        )
        # Pre-register watchlist symbols in monitor so they're polled from startup
        for wl in watchlist_service.get_all_watchlists():
            for entry in wl.entries:
                monitor.register_symbol(entry.symbol)

        alert_adapter = AlertConfigAdapter(
            engine=detection_engine,
            alert_manager=alert_manager,
            detection_service=detection_service,
            portfolio_service=portfolio_service,
            watchlist_service=watchlist_service,
            alerts_module=db.alerts,
            monitor=monitor,
        )
        alert_adapter.wire(bus)
        alert_adapter.load_all()

        if not is_live:
            alert_manager.suppressed_detectors = {
                detector.name()
                for detectors in detection_engine.asset_detectors.values()
                for detector in detectors
            }
        # TODO(openclaw): openclaw delivery will be a channel type in the DB config
        # alert_manager.add_target(LoggingAlertDelivery())

        WatchlistAdapter(detection_engine, alert_manager, monitor, detection_service, data_provider, alert_adapter=alert_adapter).wire(bus)

    # Prime services
    with logfire.span("service.startup.prime"):
        all_watchlist_symbols = list({e.symbol for wl in watchlist_service.get_all_watchlists() for e in wl.entries})
        await prime(config, bus, portfolio_service, data_provider, detection_service, extra_symbols=all_watchlist_symbols)

    # Start API server
    ctx = PortfolioMonitorContext(
        config=config,
        db=db,
        portfolio_service=portfolio_service,
        watchlist_service=watchlist_service,
        bus=bus,
        data_provider=data_provider,
        account_store=account_store,
        session_store=session_store,
    )
    api_app: Starlette = create_api_app(ctx)
    uvicorn_config = uvicorn.Config(
        api_app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    api_server: Server = uvicorn.Server(uvicorn_config)

    # Build control panel for dev-live mode (synthetic_source=None disables sim controls)
    cp_server: Server | None = None
    if is_dev:
        from portfolio_monitor.service.dev.control_panel.app import ControlPanelApp

        control_panel = ControlPanelApp(
            bus=bus,
            synthetic_source=None,
            detection_engine=detection_engine,
            detection_service=detection_service,
            alert_manager=alert_manager,
            aggregate_cache=aggregate_cache,
            portfolio_service=portfolio_service,
        )
        cp_uvicorn_config = uvicorn.Config(
            control_panel.app,
            host=config.host,
            port=config.control_panel_port,
            log_level="debug" if config.debug else "info",
        )
        cp_server = uvicorn.Server(cp_uvicorn_config)

        def _initiate_shutdown() -> None:
            control_panel.shutdown()
            cp_server.should_exit = True  # type: ignore[union-attr]
            api_server.should_exit = True

        control_panel._stop_callback = _initiate_shutdown

    vite: ViteProcess | None = None
    try:
        await alert_manager.connect_all()
        await monitor.start()
        if cp_server is not None:
            serve_task = asyncio.gather(api_server.serve(), cp_server.serve())
        else:
            serve_task = asyncio.ensure_future(api_server.serve())
        if is_dev:
            while not api_server.started:
                await asyncio.sleep(0.05)
            vite = await start_vite(_FRONTEND_DIR)
            print(f"\nControl:   http://{config.host}:{config.control_panel_port}/")
            print(f"Dashboard: http://{config.host}:{config.port}/")
            print(f"Frontend:  {vite.url}")
            print(f"API:       http://{config.host}:{config.port}/api/v1/health\n")
        await serve_task
    except asyncio.CancelledError:
        logger.info("Main task cancelled, initiating graceful shutdown...")
    except Exception as e:
        logger.error("Error in service: %s", e)
        raise
    finally:
        if vite is not None and vite.returncode is None:
            vite.terminate()
            await vite.wait()

        try:
            if monitor.running:
                await monitor.stop()
        except Exception as e:
            logger.error("Error stopping monitor: %s", e)

        try:
            await alert_manager.disconnect_all()
        except Exception as e:
            logger.error("Error disconnecting alert manager: %s", e)

        try:
            await aggregate_cache.close()
        except Exception as e:
            logger.error("Error closing aggregate cache: %s", e)


async def prime(
    config: PortfolioMonitorConfig,
    bus: EventBus,
    portfolio_service: PortfolioService,
    data_provider: PolygonDataProvider,
    detection_service: DetectionService,
    extra_symbols: list[AssetSymbol] | None = None,
) -> None:
    """Prime detection engine and seed prices for all portfolio + watchlist symbols."""
    with logfire.span("service.prime.detection_service"):
        all_symbols: list[AssetSymbol] = list(
            {asset.symbol for portfolio in portfolio_service.get_all_portfolios() for asset in portfolio.assets()}
            | set(extra_symbols or [])
        )
        await detection_service.prime(all_symbols, datetime.now(ZoneInfo("UTC")))

    logger.info("Seeding prices for %d symbols...", len(all_symbols))
    with logfire.span("service.prime.seed_prices", symbol_count=len(all_symbols)):
        for symbol in all_symbols:
            agg = await data_provider.get_aggregate(symbol)
            if agg:
                await bus.publish(AggregateUpdated(symbol=symbol, aggregate=agg))

    if config.deep_prime:
        logger.info("Deep priming - fetching all symbols from Polygon...")
        with logfire.span("service.prime.deep_prime", symbol_count=len(all_symbols)):
            for symbol in all_symbols:
                await _deep_prime(symbol, data_provider)

async def _deep_prime(symbol: AssetSymbol, data_provider: PolygonDataProvider) -> None:
    """Deep prime a symbol by fetching all data from Polygon."""
    # Load all aggregates for this symbol from current "last" price to prior last close
    current_aggregate: Aggregate = await data_provider.get_aggregate(symbol)

    if current_aggregate is None:
        current_time = datetime.now()
        if MarketInfo.is_market_closed(symbol, current_time):
            close_time = MarketInfo.get_market_close(symbol, current_time)
        else:
            logger.warning("Current aggregate is None for symbol %s, but market is open. This should not happen.", symbol)
            return
    else:
        close_time = current_aggregate.date_close
    
    prior_close_time = MarketInfo.get_market_close(symbol, close_time - timedelta(days=2))
    
    _ = await data_provider.get_range(symbol, prior_close_time, close_time, cache_write=True)


def generate_auth_key(config_path: Path) -> None:
    """Generate a random 256-bit auth key and save to the private config file."""
    private_path = config_path.with_name(config_path.stem + "_private.yaml")

    if private_path.exists():
        config = OmegaConf.load(private_path)
    else:
        config = OmegaConf.create()

    key = secrets.token_hex(32)
    OmegaConf.update(config, "private.portfolio_monitor.auth_key", key)
    OmegaConf.save(config, private_path)

    print(f"Auth key written to {private_path}")


def arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio Monitor Service")
    subparsers = parser.add_subparsers(dest="command")

    # generate-auth-key subcommand
    subparsers.add_parser(
        "generate-auth-key",
        help="Generate a random auth key and save to private config",
    )

    # run subcommand (default)
    run_parser = subparsers.add_parser("run", help="Run the monitor service")
    run_parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    run_parser.add_argument("--trace", action="store_true", help="Enable trace logging")
    run_parser.add_argument("--host", type=str, help="Control interface host")
    run_parser.add_argument("--port", type=int, help="Control interface port")
    run_parser.add_argument("--auth-key", type=str, help="Authorization key")
    run_parser.add_argument(
        "--prime",
        action="store_true",
        help="Run with deep prime mode (fetch all symbols from Polygon)",
    )
    run_parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in dev mode with synthetic data (no API keys needed)",
    )
    run_parser.add_argument(
        "--dev-live",
        action="store_true",
        help="Run with live Polygon data but start Vite dev server for frontend development",
    )
    run_parser.add_argument(
        "--tick-interval",
        type=float,
        default=5.0,
        help="Dev mode: seconds between synthetic price ticks (default: 5.0)",
    )
    run_parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Logfire instrumentation",
    )

    return parser


def _auth_key_exit() -> None:
    program_name = Path(sys.argv[0]).name
    print(f"Authorization key is not configured: ./{program_name} generate-auth-key")
    SystemExit(-1)


def main() -> None:
    parser = arg_parser()
    args = parser.parse_args()

    config_path = Path("config/config.yaml")

    if args.command == "generate-auth-key":
        generate_auth_key(config_path)
        return

    # Default to "run" when no subcommand given
    if args.command is None:
        args = parser.parse_args(["run"])

    # Dev mode — synthetic data, no Polygon API
    if args.dev:
        from portfolio_monitor.service.dev import run_dev_service
        from portfolio_monitor.service.dev.config import DevConfig

        config = DevConfig.from_config_file(config_path, args)
    
    else:
        try:
            config = PortfolioMonitorConfig(config_path, args)
        except PrivateConfigError as e:
            if e.key == "private.portfolio_monitor.auth_key":
                return _auth_key_exit()
            else:
                raise e


    # Set log level based on debug flag
    log_level = TRACE if config.trace else (logging.DEBUG if (config.debug or args.dev) else logging.INFO)
    log_format = logging.BASIC_FORMAT if log_level >= logging.INFO else "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(level=log_level, format=log_format)

    logfire.configure(
        service_name="Portfolio Monitor",
        scrubbing=False,
        console={"min_log_level": "warning"},
        send_to_logfire=args.logfire,
    )

    if args.logfire:
        URLLib3Instrumentor().instrument()

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)
        
    if args.dev_live:
        config.dev_console = True

    try:
        if args.dev:
            asyncio.run(run_dev_service(config))
        else:
            if not config.auth_key:
                return _auth_key_exit()

            asyncio.run(run_service(config, is_live=True, is_dev=args.dev_live))
    except KeyboardInterrupt:
        logger.info("Shutting down [Ctrl+C]")


if __name__ == "__main__":
    main()
