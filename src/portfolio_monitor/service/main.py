import argparse
import asyncio
import logging
import secrets
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import logfire
import uvicorn
from appconf.omegaconf.errors import PrivateConfigError
from omegaconf import OmegaConf
from starlette.applications import Starlette
from uvicorn.server import Server

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import AggregateCache
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.loader import load_portfolios
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts import AlertRouter, LoggingAlertDelivery
from portfolio_monitor.service.api import create_api_app
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.service.types import AssetSymbol

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def run_service(config: PortfolioMonitorConfig) -> None:
    """Run the monitor service until interrupted"""

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)

    # Load portfolios
    if not config.portfolio_path:
        raise ValueError("Portfolio path not configured")

    portfolios = load_portfolios(config.portfolio_path)

    print("=== Portfolios     ===")
    for portfolio in portfolios:
        print(portfolio)
    print("=== End Portfolios ===")

    # Load aggregate cache
    aggregate_cache = AggregateCache(config.aggregate_cache_path)
    aggregate_cache.initialize()
    await aggregate_cache.load()

    # Create event bus
    bus = EventBus()

    # Wire aggregate cache to persist on AggregateUpdated
    async def _persist_aggregate(event: AggregateUpdated) -> None:
        await aggregate_cache.add(event.aggregate)

    bus.subscribe(AggregateUpdated, _persist_aggregate)

    # Create data provider
    data_provider = DataProvider(config, aggregate_cache)

    # Build detection engine from config
    monitors_config = config.monitors
    default_detectors_config = monitors_config.get("default", {})
    default_detectors = [
        {"name": name, "args": args} for name, args in default_detectors_config.items()
    ]
    detection_engine = DeviationEngine(default_detectors=default_detectors)

    # Register per-asset detectors
    for ticker, detector_configs in monitors_config.items():
        if ticker == "default":
            continue
        for name, args in detector_configs.items():
            detection_engine.add_detector(
                _resolve_symbol(portfolios, ticker),
                {"name": name, "args": args},
            )

    # Create services — subscriptions happen in constructors
    detection_service = DetectionService(
        bus=bus,
        detection_engine=detection_engine,
        data_provider=data_provider,
    )
    portfolio_service = PortfolioService(bus=bus, portfolios=portfolios)  # noqa: F841
    alert_router = AlertRouter(bus=bus)
    alert_router.add_target(LoggingAlertDelivery())

    monitor = MonitorService(
        bus=bus,
        data_provider=data_provider,
        portfolios=portfolios,
    )

    # Prime detection engine with historical data
    all_symbols: list[AssetSymbol] = list(
        {asset.symbol for portfolio in portfolios for asset in portfolio.assets()}
    )
    await detection_service.prime(all_symbols, datetime.now(ZoneInfo("UTC")))

    # Start API server
    assert config.auth_key is not None, "Auth key is required"
    api_app: Starlette = create_api_app(config)
    uvicorn_config = uvicorn.Config(
        api_app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    api_server: Server = uvicorn.Server(uvicorn_config)

    try:
        await alert_router.connect_all()
        await monitor.start()
        await api_server.serve()
    except asyncio.CancelledError:
        logger.info("Main task cancelled, initiating graceful shutdown...")
    except Exception as e:
        logger.error("Error in service: %s", e)
        raise
    finally:
        try:
            if monitor.running:
                await monitor.stop()
        except Exception as e:
            logger.error("Error stopping monitor: %s", e)

        try:
            await alert_router.disconnect_all()
        except Exception as e:
            logger.error("Error disconnecting alert router: %s", e)

        try:
            await aggregate_cache.close()
        except Exception as e:
            logger.error("Error closing aggregate cache: %s", e)


def _resolve_symbol(portfolios: list, ticker: str) -> AssetSymbol:
    """Resolve a ticker string to an AssetSymbol from loaded portfolios."""
    for portfolio in portfolios:
        for asset in portfolio.assets():
            if asset.symbol.ticker == ticker:
                return asset.symbol
    raise ValueError(f"Ticker {ticker} not found in portfolios")


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
    run_parser.add_argument("--host", type=str, help="Control interface host")
    run_parser.add_argument("--port", type=int, help="Control interface port")
    run_parser.add_argument("--auth-key", type=str, help="Authorization key")
    run_parser.add_argument(
        "--dev", action="store_true",
        help="Run in dev mode with synthetic data (no API keys needed)",
    )
    run_parser.add_argument(
        "--tick-interval", type=float, default=5.0,
        help="Dev mode: seconds between synthetic price ticks (default: 5.0)",
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

    # Dev mode — bypass PortfolioMonitorConfig entirely
    if getattr(args, "dev", False):
        from portfolio_monitor.service.dev import run_dev_service
        from portfolio_monitor.service.dev.config import DevConfig

        dev_config = DevConfig.from_config_file(config_path, args)
        try:
            asyncio.run(run_dev_service(dev_config))
        except KeyboardInterrupt:
            logger.info("Shutting down dev mode [Ctrl+C]")
        return

    try:
        config = PortfolioMonitorConfig(config_path, args)
    except PrivateConfigError as e:
        if e.key == "private.portfolio_monitor.auth_key":
            return _auth_key_exit()
        else:
            raise e

    if not config.auth_key:
        return _auth_key_exit()

    # Set log level based on debug flag
    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=log_level, format=logging.BASIC_FORMAT)

    logfire.configure(service_name="Portfolio Monitor")

    try:
        asyncio.run(run_service(config))
    except KeyboardInterrupt:
        logger.info("Shutting down [Ctrl+C]")


if __name__ == "__main__":
    main()
