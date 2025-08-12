import argparse
import asyncio
import logging
from pathlib import Path

from nexus_portfolio_monitor.core.config import load_config
from nexus_portfolio_monitor.data.aggregate_cache import AggregateCache
from nexus_portfolio_monitor.portfolio.loader import load_portfolios

from nexus_portfolio_monitor.service.monitor import MonitorService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def run_service(args: argparse.Namespace):
    """Run the monitor service until interrupted"""

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)

    config = load_config()
    portfolio_path = config.get("nexus.portfolio_path")
    aggregate_cache_path = config.get("nexus.aggregate_cache_path")
    
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

    service = MonitorService(config, portfolios, aggregate_cache)
    
    try:
        await service.start()
        # Keep the service running
        if service._task:
            await asyncio.wait_for(service._task, timeout=None)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        if service.running:
            await service.stop()


def main():
    """Entry point for the monitor service"""
    parser = argparse.ArgumentParser(description="Nexus Portfolio Monitor Service")
    parser.add_argument(
        "-d", "--debug", 
        action="store_true", 
        help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set log level based on debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format=logging.BASIC_FORMAT)
    
    asyncio.run(run_service(args))


if __name__ == "__main__":
    main()
