import asyncio
import logging
from polygon import RESTClient as PolygonRESTClient, WebSocketClient as PolygonWebSocketClient
from polygon.exceptions import BadResponse
import time

from nexus_portfolio_monitor.core.config import NexusConfig, load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class MonitorService:
    """Monitor service that runs in an asyncio event loop"""
    
    def __init__(self, config: NexusConfig):
        """
        Initialize the monitor service
        """
        self.config = config
        self._polygon_client: PolygonRESTClient = PolygonRESTClient(config.get("polygon.api-key"))
        self._polygon_websocket_client: PolygonWebSocketClient = PolygonWebSocketClient(config.get("polygon.api-key"))

        self.running = False
        self._task: asyncio.Task | None = None
        
    async def start(self) -> None:
        """Start the monitoring service"""
        if self.running:
            logger.warning("Monitor service is already running")
            return
            
        self.running = True
        logger.info("Starting monitor")
        self._task = asyncio.create_task(self._run())
        
    async def stop(self) -> None:
        """Stop the monitoring service"""
        if not self.running:
            logger.warning("Monitor service is not running")
            return
            
        logger.info("Stopping monitor")
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Monitor stopped")
        
    async def _run(self) -> None:
        """Internal run loop"""
        try:
            # self._polygon_websocket_client.run(handle_msg=lambda msg: logger.info(msg))
            # self._polygon_websocket_client.connect(processor=lambda msg: logger.info(msg))

            last_update = 0
            update_interval = 60
            while self.running:
                try:
                    self._dump_symbol("AAPL")
                except BadResponse as e:
                    logger.error(f"Error dumping symbol AAPL: {e}")
                    import traceback
                    traceback.print_exc()

                last_update = time.monotonic()
                next_update = last_update + update_interval
                await asyncio.sleep(next_update - last_update)
        except asyncio.CancelledError:
            logger.debug("Monitor loop cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error in monitor loop: {e}")
            import traceback
            traceback.print_exc()
            self.running = False

    def _dump_symbol(self, ticker: str):
        """Dump all available data for a symbol"""
        # List Aggregates (Bars)
        aggs = []
        for a in self._polygon_client.list_aggs(ticker=ticker, multiplier=1, timespan="minute", from_="2025-06-01", to="2025-07-01", limit=50000):
            aggs.append(a)
        print(aggs)

        # Get Last Trade
        trade = self._polygon_client.get_last_trade(ticker=ticker)
        print(trade)

        # List Trades
        trades = self._polygon_client.list_trades(ticker=ticker)
        for trade in trades:
            print(trade)

        # Get Last Quote
        quote = self._polygon_client.get_last_quote(ticker=ticker)
        print(quote)

        # List Quotes
        quotes = self._polygon_client.list_quotes(ticker=ticker)
        for quote in quotes:
            print(quote)

async def run_service():
    """Run the monitor service until interrupted"""

    config = load_config()

    service = MonitorService(config)
    
    try:
        await service.start()
        # Keep the service running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()


def main():
    """Entry point for the monitor service"""
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
