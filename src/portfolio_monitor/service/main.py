import argparse
import asyncio
import logging
import secrets
import sys
from pathlib import Path

import logfire
from appconf.omegaconf.errors import PrivateConfigError
from omegaconf import OmegaConf

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.data.aggregate_cache import AggregateCache
from portfolio_monitor.portfolio.loader import load_portfolios
from portfolio_monitor.service.alerts import LoggingAlertDelivery
from portfolio_monitor.service.monitor import MonitorService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def run_service(config: PortfolioMonitorConfig):
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

    alert_delivery = LoggingAlertDelivery()

    service = MonitorService(config, alert_delivery, portfolios, aggregate_cache)

    try:
        # Start the service and wait for it to complete or be cancelled
        await service.start()

        # Wait for the task to complete if a task was created
        service_task = service.task()
        if service_task:
            while not service_task.done():
                await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        # This is expected on Ctrl+C, asyncio.run() will cancel the main task
        logger.info("Main task cancelled, initiating graceful shutdown...")
    except Exception as e:
        logger.error(f"Error in service: {e}")
        raise
    finally:
        # Ensure all resources are properly closed, even on cancellation
        try:
            if service.running:
                await service.stop()
        except Exception as e:
            logger.error(f"Error stopping service: {e}")
            import traceback

            traceback.print_exc()

        try:
            await aggregate_cache.close()
        except Exception as e:
            logger.error(f"Error closing aggregate cache: {e}")


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

    return parser


def _auth_key_exit():
    program_name = Path(sys.argv[0]).name
    print(f"Authorization key is not configured: ./{program_name} generate-auth-key")
    SystemExit(-1)


def main():
    parser = arg_parser()
    args = parser.parse_args()

    config_path = Path("config/config.yaml")

    if args.command == "generate-auth-key":
        generate_auth_key(config_path)
        return

    # Default to "run" when no subcommand given
    if args.command is None:
        args = parser.parse_args(["run"])

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
