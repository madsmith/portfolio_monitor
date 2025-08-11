import asyncio
from datetime import datetime, time as dtime, timedelta
import logging
from polygon import RESTClient as PolygonRESTClient, WebSocketClient as PolygonWebSocketClient
from polygon.rest.aggs import PreviousCloseAgg
from polygon.rest.models.trades import CryptoTrade
from polygon.websocket import CurrencyAgg, Market
from polygon.websocket.models import Feed, WebSocketMessage
from typing import List
from urllib3.exceptions import RequestError
from zoneinfo import ZoneInfo

from nexus_portfolio_monitor.core.config import NexusConfig
from nexus_portfolio_monitor.data.aggregate_cache import Aggregate, AggregateCache
from nexus_portfolio_monitor.portfolio.portfolio import Portfolio
from nexus_portfolio_monitor.core.currency import Currency
from nexus_portfolio_monitor.service.types import AssetUpdateRecord


logger = logging.getLogger(__name__)

class MonitorService:
    """Monitor service that runs in an asyncio event loop"""
    
    def __init__(self, config: NexusConfig, portfolios: List[Portfolio], aggregate_cache: AggregateCache):
        """
        Initialize the monitor service
        """
        self.config: NexusConfig = config
        self.portfolios: List[Portfolio] = portfolios
        self.aggregate_cache: AggregateCache = aggregate_cache
        self._polygon_client: PolygonRESTClient = PolygonRESTClient(config.get("polygon.api-key"))
        self._polygon_websocket_client: PolygonWebSocketClient = PolygonWebSocketClient(
            config.get("polygon.api-key"),
            Feed.RealTime,
            market = Market.Crypto
        )

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
        await self.aggregate_cache.wait_for_completion()

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
        
    async def test_streaming(self):
        print("Streaming test")
        try:

            self._polygon_websocket_client.subscribe("XAS.XRP-USD, XAS.BTC-USD, XAS.ETH-USD")
            # self._polygon_websocket_client.subscribe("XAS.*")

            async def handle_msg(msgs: List[WebSocketMessage]):
                for msg in msgs:
                    if isinstance(msg, CurrencyAgg):
                        change_percent = (msg.close - msg.open) / msg.open
                        if abs(change_percent) > 0.00001:
                            print(f"  {msg.pair + ":":<10} {change_percent:<20.2%} Open: {msg.open} Close: {msg.close}")

            await self._polygon_websocket_client.connect(handle_msg)
        except Exception as e:
            logger.exception(f"Error in streaming test: {e}")


    async def _run(self) -> None:

        # return await self.test_streaming()

        """Internal run loop"""
        update_interval = 60
        stock_update_interval = 24 * 60 * 60
        
        stocks: dict[str, AssetUpdateRecord] = {}
        currencies: dict[str, AssetUpdateRecord] = {}
        crypto: dict[str, AssetUpdateRecord] = {}

        # Initialize update records for all assets
        for portfolio in self.portfolios:
            for asset in portfolio.assets():
                record = AssetUpdateRecord(asset.ticker)
                aggregate = self.aggregate_cache.get_current(asset.ticker)
                if aggregate:
                    record.price = Currency(aggregate.close, Currency.DEFAULT_CURRENCY_TYPE)
                    record.time_updated = aggregate.date
                if asset.asset_type == "stock":
                    stocks[asset.ticker] = record
                elif asset.asset_type == "currency":
                    currencies[asset.ticker] = record
                elif asset.asset_type == "crypto":
                    crypto[asset.ticker] = record

        print(f"Stocks: {len(stocks)}")
        for ticker, record in stocks.items():
            print(f"  {ticker}: {record}")
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
                    # if not self.is_market_open():
                    #     continue

                    previous_close = get_previous_close_datetime()

                    if (
                        record.time_updated 
                        and (previous_close - record.time_updated).total_seconds() < stock_update_interval
                    ):
                        print(f"Skipping update for {stock_ticker} - too soon since previous close")
                        continue

                    # logger.info(f"Updating stock {stock_ticker}")
                    # trade = self._polygon_client.get_last_trade(ticker=stock_ticker)
                    print(f"Updating stock {stock_ticker}")
                    try:
                        trade = self._polygon_client.get_previous_close_agg(ticker=stock_ticker)
                    except RequestError as e:
                        logger.warning(f"Error updating stock {stock_ticker}: Waiting 60 seconds")
                        await asyncio.sleep(60)
                        continue
                    except BaseException as e:
                        logger.exception(f"Error updating stock {stock_ticker}: {e} [{type(e)}]")
                        await asyncio.sleep(60)
                        continue
                    if isinstance(trade, list):
                        trade = trade[0]
                    if isinstance(trade, PreviousCloseAgg):
                        print(f"  {stock_ticker}: {trade}")
                        record.price = Currency(trade.close, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = datetime.now(ZoneInfo("UTC"))

                        if (
                            trade.timestamp is None 
                            or trade.open is None 
                            or trade.high is None 
                            or trade.low is None 
                            or trade.close is None 
                            or trade.volume is None
                        ):
                            logger.warning(f"Invalid trade data for {stock_ticker}: {trade}")
                            continue
                        
                        record_date = polygon_timestamp_to_datetime(trade.timestamp)
                        aggregate = Aggregate(
                            stock_ticker,
                            record_date,
                            trade.open,
                            trade.high,
                            trade.low,
                            trade.close,
                            trade.volume
                        )
                        await self.aggregate_cache.add(aggregate)
                    else:
                        logger.warning(f"Unknown trade type: {type(trade)} {trade}")
                        await asyncio.sleep(60)
                
                for crypto_ticker, record in crypto.items():
                    now = datetime.now(ZoneInfo("UTC"))

                    if record.time_updated and (now - record.time_updated).total_seconds() < update_interval:
                        continue

                    # logger.info(f"Updating crypto {crypto_ticker}")
                    trade = self._polygon_client.get_last_crypto_trade(
                        from_=crypto_ticker,
                        to=Currency.DEFAULT_CURRENCY_TYPE.name
                    )

                    if isinstance(trade, CryptoTrade):
                        record.price = Currency(trade.price, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = datetime.now(ZoneInfo("UTC"))
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

def polygon_timestamp_to_datetime(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000, ZoneInfo("UTC"))

def get_previous_close_datetime() -> datetime:
    """
    Returns the datetime of the most recent market close (4:00 PM Eastern)
    If it's after 4:00 PM today, returns today's close time.
    Handles weekends but does not account for holidays.
    """
    eastern = ZoneInfo("America/New_York")
    now = datetime.now(tz=eastern)
    market_close_time = dtime(16, 0)  # 4:00 PM Eastern
    
    # If it's after market close today (and a weekday), use today's date
    if now.weekday() < 5 and now.time() >= market_close_time:  # Weekday after 4:00 PM
        return datetime.combine(now.date(), market_close_time, tzinfo=eastern)
    
    # Otherwise, find the previous market day
    if now.weekday() == 0:  # Monday
        base_date = now.date() - timedelta(days=3)  # Previous Friday
    elif now.weekday() == 6:  # Sunday
        base_date = now.date() - timedelta(days=2)  # Previous Friday
    else:
        base_date = now.date() - timedelta(days=1)  # Previous day
    
    # Create a datetime at 4:00 PM on the determined date (market close time)
    market_close = datetime.combine(
        base_date,
        market_close_time,
        tzinfo=eastern
    )
    
    return market_close