import asyncio
from dataclasses import dataclass
from datetime import datetime, time as dtime
import logging
from pathlib import Path
from polygon import RESTClient as PolygonRESTClient, WebSocketClient as PolygonWebSocketClient
from polygon.exceptions import BadResponse
from polygon.rest.models import LastTrade
from polygon.rest.models.trades import CryptoTrade
import time
from typing import List
from zoneinfo import ZoneInfo

from nexus_portfolio_monitor.core.config import NexusConfig, load_config
from nexus_portfolio_monitor.portfolio.loader import load_portfolios
from nexus_portfolio_monitor.portfolio.portfolio import Portfolio
from nexus_portfolio_monitor.core.currency import Currency



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@dataclass
class AssetUpdateRecord:
    ticker: str
    price: Currency | None = None
    time_updated: datetime | None = None

class MonitorService:
    """Monitor service that runs in an asyncio event loop"""
    
    def __init__(self, config: NexusConfig, portfolios: List[Portfolio]):
        """
        Initialize the monitor service
        """
        self.config: NexusConfig = config
        self.portfolios: List[Portfolio] = portfolios
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
        update_interval = 60
        
        stocks: dict[str, AssetUpdateRecord] = {}
        currencies: dict[str, AssetUpdateRecord] = {}
        crypto: dict[str, AssetUpdateRecord] = {}

        # Initialize update records for all assets
        for portfolio in self.portfolios:
            for asset in portfolio.assets():
                if asset.asset_type == "stock":
                    stocks[asset.ticker] = AssetUpdateRecord(asset.ticker)
                elif asset.asset_type == "currency":
                    currencies[asset.ticker] = AssetUpdateRecord(asset.ticker)
                elif asset.asset_type == "crypto":
                    crypto[asset.ticker] = AssetUpdateRecord(asset.ticker)

        # print(f"Stocks: {len(stocks)}")
        # for ticker, record in stocks.items():
        #     print(f"  {ticker}: {record}")
        # print(f"Currencies: {len(currencies)}")
        # for ticker, record in currencies.items():
        #     print(f"  {ticker}: {record}")
        # print(f"Crypto: {len(crypto)}")
        # for ticker, record in crypto.items():
        #     print(f"  {ticker}: {record}")

        try:
            while self.running:
                
                # Update all assets
                for stock_ticker, record in stocks.items():
                    if not self.is_market_open():
                        continue

                    now = datetime.now()

                    if record.time_updated and (now - record.time_updated).total_seconds() < update_interval:
                        continue

                    # logger.info(f"Updating stock {stock_ticker}")
                    trade = self._polygon_client.get_last_trade(ticker=stock_ticker)
                    if isinstance(trade, LastTrade):
                        record.price = Currency(trade.price, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = datetime.now()
                    else:
                        logger.warning(f"Unknown trade type: {type(trade)} {trade}")
                        await asyncio.sleep(60)
                
                for crypto_ticker, record in crypto.items():
                    now = datetime.now()

                    if record.time_updated and (now - record.time_updated).total_seconds() < update_interval:
                        continue

                    # logger.info(f"Updating crypto {crypto_ticker}")
                    trade = self._polygon_client.get_last_crypto_trade(
                        from_=crypto_ticker,
                        to=Currency.DEFAULT_CURRENCY_TYPE.name
                    )

                    if isinstance(trade, CryptoTrade):
                        record.price = Currency(trade.price, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = datetime.now()
                    else:
                        logger.warning(f"Unknown trade type: {type(trade)} {trade}")
                        await asyncio.sleep(60)

                # Update portfolios with all prices
                price_data: dict[str, Currency] = {
                    ticker: record.price
                    for d in (stocks, currencies, crypto)
                    for ticker, record in d.items()
                    if record.price
                }

                for portfolio in self.portfolios:
                    portfolio.update_prices(price_data)

                logger.info("Portfolios updated") 


                print("=== Portfolios     ===")
                for portfolio in self.portfolios:
                    print(portfolio)
                print("=== End Portfolios ===")

                await asyncio.sleep(update_interval)

        except asyncio.CancelledError:
            logger.debug("Monitor loop cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error in monitor loop: {e}")
            import traceback
            traceback.print_exc()
            self.running = False

    def is_market_open(self, extended: bool = False) -> bool:
        """Return True if the U.S. stock market is open now (Eastern Time).

        Args:
            extended: If True, includes pre-market (4–9:30) and after-hours (16–20).
        """
        eastern = ZoneInfo("America/New_York")
        now = datetime.now(tz=eastern)

        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        t = now.time()

        if extended:
            return dtime(4, 0) <= t <= dtime(20, 0)
        else:
            return dtime(9, 30) <= t <= dtime(16, 0)

async def run_service():
    """Run the monitor service until interrupted"""

    config = load_config()
    portfolio_path = config.get("nexus.portfolio_path")
    if not portfolio_path:
        raise ValueError("Portfolio path not configured")
    path = Path(portfolio_path)

    portfolios = load_portfolios(path)

    print("=== Portfolios     ===")
    for portfolio in portfolios:
        print(portfolio)
    print("=== End Portfolios ===")

    service = MonitorService(config, portfolios)
    
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
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
