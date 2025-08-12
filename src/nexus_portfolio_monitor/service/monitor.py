import asyncio
from datetime import datetime, time as dtime, timedelta
import logging

from nexus_portfolio_monitor.data.provider import DataProvider

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
from nexus_portfolio_monitor.detectors import (
    DeviationEngine,
    AverageTrueRangeMoveDetector,
    MovingAverageDeviationDetector,
    PercentChangeFromPreviousCloseDetector,
    VolumeSpikeDetector,
    ZScoreReturnDetector
)
from nexus_portfolio_monitor.service.types import AssetSymbol, AssetTypes


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

        self._data_provider = DataProvider(config, aggregate_cache)

        self._detection_engine: DeviationEngine = DeviationEngine(
            detectors = [
                PercentChangeFromPreviousCloseDetector(),
                VolumeSpikeDetector(),
                MovingAverageDeviationDetector(),
                AverageTrueRangeMoveDetector(),
                ZScoreReturnDetector()
            ]
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

    async def _fetch_aggregate(self, symbol: AssetSymbol, from_: datetime, to: datetime) -> Aggregate | None:
        while True:
            try:
                agg_windows = self._polygon_client.get_aggs(
                    ticker=symbol.lookup_symbol,
                    multiplier=1,
                    timespan="minute",
                    limit=1,
                    from_=from_,
                    to=to
                )

                if isinstance(agg_windows, list):
                    for agg_window in agg_windows:
                        if (
                            agg_window.timestamp is None or
                            agg_window.open is None or
                            agg_window.high is None or
                            agg_window.low is None or
                            agg_window.close is None or
                            agg_window.volume is None
                        ):
                            logger.warning(f"Invalid aggregate for {symbol}: {agg_window}")
                            continue

                        agg_date = polygon_timestamp_to_datetime(agg_window.timestamp)
                        aggregate = Aggregate(
                            symbol,
                            agg_date,
                            agg_window.open,
                            agg_window.high,
                            agg_window.low,
                            agg_window.close,
                            agg_window.volume
                        )
                        return aggregate
                    
            except RequestError as e:
                logger.warning(f"Error fetching aggregate for {symbol}: Waiting 60 seconds")
                await asyncio.sleep(60)
                continue
            except BaseException as e:
                logger.exception(f"Error fetching aggregate for {symbol}: {e} [{type(e)}]")
                await asyncio.sleep(60)
                return None
            break


    async def _run(self) -> None:
        """Internal run loop"""

        # return await self.test_streaming()

        
        update_interval = 60
        stock_update_interval = 24 * 60 * 60
        
        stocks: dict[str, AssetUpdateRecord] = {}
        currencies: dict[str, AssetUpdateRecord] = {}
        crypto: dict[str, AssetUpdateRecord] = {}

        # Initialize update records for all assets
        for portfolio in self.portfolios:
            for asset in portfolio.assets():
                record = AssetUpdateRecord(asset.symbol)
                aggregate = self.aggregate_cache.get_current(asset.symbol)
                if aggregate:
                    record.price = Currency(aggregate.close, Currency.DEFAULT_CURRENCY_TYPE)
                    record.time_updated = aggregate.date
                if asset.asset_type == "stock":
                    stocks[asset.symbol.ticker] = record
                elif asset.asset_type == "currency":
                    currencies[asset.symbol.ticker] = record
                elif asset.asset_type == "crypto":
                    crypto[asset.symbol.ticker] = record

        # Fetch historical aggregates for all asset, priming the detector
        start = datetime.now(ZoneInfo("UTC")) - timedelta(hours=3)
        end = datetime.now(ZoneInfo("UTC"))
        
        for asset_record in list(stocks.values()) + list(currencies.values()) + list(crypto.values()):
            aggs = await self._data_provider.get_range(asset_record.symbol, start, end)
            for agg in aggs:
                self._detection_engine.detect(agg)

        # print(f"Stocks: {len(stocks)}")
        # for ticker, record in stocks.items():
        #     print(f"  {ticker}: {record}")
        # print(f"Currencies: {len(currencies)}")
        # for ticker, record in currencies.items():
        #     print(f"  {ticker}: {record}")
        # print(f"Crypto: {len(crypto)}")
        # for ticker, record in crypto.items():
        #     print(f"  {ticker}: {record}")

        last_portfolio_dump_time: datetime = datetime.min
        try:
            while self.running:
                
                # Update all assets
                for record in stocks.values():
                    # if not self.is_market_open():
                    #     continue

                    previous_close = get_previous_close_datetime()
                    symbol = record.symbol

                    if (
                        record.time_updated 
                        and (previous_close - record.time_updated).total_seconds() < stock_update_interval
                    ):
                        logger.debug(f"Skipping update for {symbol} - too soon since previous close")
                        continue

                    logger.debug(f"Updating stock {symbol}")
                    try:
                        trade = self._polygon_client.get_previous_close_agg(ticker=symbol.lookup_symbol)
                    except RequestError as e:
                        logger.warning(f"Error updating stock {symbol}: Waiting 60 seconds")
                        await asyncio.sleep(60)
                        continue
                    except BaseException as e:
                        logger.exception(f"Error updating stock {symbol}: {e} [{type(e)}]")
                        continue

                    if isinstance(trade, list):
                        trade = trade[0]
                    if isinstance(trade, PreviousCloseAgg):
                        if (
                            trade.timestamp is None 
                            or trade.open is None 
                            or trade.high is None 
                            or trade.low is None 
                            or trade.close is None 
                            or trade.volume is None
                        ):
                            logger.warning(f"Invalid trade data for {symbol}: {trade}")
                            continue

                        record_date = polygon_timestamp_to_datetime(trade.timestamp)

                        record.price = Currency(trade.close, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = record_date
                        
                        aggregate = Aggregate(
                            symbol,
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
                
                for record in crypto.values():
                    now = datetime.now(ZoneInfo("UTC"))
                    symbol = record.symbol

                    if record.time_updated and (now - record.time_updated).total_seconds() < update_interval:
                        continue

                    logger.debug(f"Updating crypto {symbol}")

                    try:
                        agg_windows = self._polygon_client.get_aggs(
                            symbol.lookup_symbol,
                            multiplier=1,
                            timespan="minute",
                            from_=now - timedelta(minutes=1),
                            to=now
                        )
                    except RequestError as e:
                        logger.warning(f"Error updating crypto {symbol}: Waiting 60 seconds")
                        await asyncio.sleep(60)
                        continue
                    except BaseException as e:
                        logger.exception(f"Error updating crypto {symbol}: {e} [{type(e)}]")
                        await asyncio.sleep(60)
                        continue

                    if isinstance(agg_windows, list):
                        if len(agg_windows) == 0:
                            logger.warning(f"No aggregate windows found for {symbol}")
                            continue
                        elif len(agg_windows) > 1:
                            logger.warning(f"Multiple aggregate windows found for {symbol}")
                        
                        trade = agg_windows[0]

                        if (
                            trade.timestamp is None 
                            or trade.open is None 
                            or trade.high is None 
                            or trade.low is None 
                            or trade.close is None 
                            or trade.volume is None
                        ):
                            logger.warning(f"Invalid trade data for {symbol}: {trade}")
                            continue

                        record_date = polygon_timestamp_to_datetime(trade.timestamp)

                        # Update pricing data for display
                        record.price = Currency(trade.close, Currency.DEFAULT_CURRENCY_TYPE)
                        record.time_updated = record_date
                        
                        # Update aggregate cache
                        aggregate = Aggregate(
                            symbol,
                            record_date,
                            trade.open,
                            trade.high,
                            trade.low,
                            trade.close,
                            trade.volume
                        )
                        await self.aggregate_cache.add(aggregate)

                        # Run detection engine
                        alerts = self._detection_engine.detect(aggregate)
                        if alerts:
                            logger.info(f"Alerts for {symbol}:")
                            for alert in alerts:
                                logger.warning(f"    {alert}")
                    else:
                        logger.warning(f"Unknown aggregate for {symbol}: {agg_windows}")

                # Update portfolios with all prices
                price_data: dict[str, Currency] = {
                    ticker: record.price
                    for d in (stocks, currencies, crypto)
                    for ticker, record in d.items()
                    if record.price
                }

                for portfolio in self.portfolios:
                    portfolio.update_prices(price_data)

                logger.debug("Portfolios updated") 


                if (datetime.now() - last_portfolio_dump_time) > timedelta(minutes=15):
                    last_portfolio_dump_time = datetime.now()
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