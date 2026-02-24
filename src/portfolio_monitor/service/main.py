import argparse
import asyncio
import logging
from pathlib import Path

import logfire

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


async def run_service(args: argparse.Namespace):
    """Run the monitor service until interrupted"""

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)

    config = PortfolioMonitorConfig("config/config.yaml", args)
    portfolio_path = config.portfolio_path
    aggregate_cache_path = config.aggregate_cache_path

    if not portfolio_path:
        raise ValueError("Portfolio path not configured")
    path = Path(portfolio_path)

    portfolios = load_portfolios(path)

    print("=== Portfolios     ===")
    for portfolio in portfolios:
        print(portfolio)
    print("=== End Portfolios ===")

    aggregate_cache = AggregateCache(aggregate_cache_path)
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


def main():
    """Entry point for the monitor service"""
    parser = argparse.ArgumentParser(description="Portfolio Monitor Service")

    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()

    # Set log level based on debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format=logging.BASIC_FORMAT)

    logfire.configure(service_name="Portfolio Monitor")

    try:
        asyncio.run(run_service(args))
    except KeyboardInterrupt:
        logger.info("Shutting down [Ctrl+C]")


if __name__ == "__main__":
    main()
