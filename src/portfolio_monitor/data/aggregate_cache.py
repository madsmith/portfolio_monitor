import asyncio
import contextvars
import logging
import sqlite3

import logfire
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo

from sortedcontainers import SortedDict

from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.core import datetime_from_ms, ms_from_datetime
from portfolio_monitor.utils import logfire_set_attribute

# Price decimal places by asset type for JSON serialization
_PRICE_PRECISION: dict[AssetTypes, int] = {
    AssetTypes.Stock: 2,
    AssetTypes.Currency: 4,
    AssetTypes.Crypto: 6,
}

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    """Base class for OHLCV aggregates."""
    symbol: AssetSymbol
    date_open: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, AssetSymbol):
            raise TypeError(
                f"symbol must be an AssetSymbol, got {type(self.symbol).__name__}: {self.symbol!r}"
            )
        if self.date_open.tzinfo is None:
            raise ValueError(
                f"date_open must be timezone-aware. Got: {self.date_open}"
            )

    @property
    def timestamp_ms(self) -> int:
        """Milliseconds since epoch for date_open."""
        return int(self.date_open.timestamp() * 1000)


@dataclass
class Aggregate(OHLCV):
    timespan: timedelta

    def __post_init__(self) -> None:
        super().__post_init__()
        if isinstance(self.timespan, int):
            object.__setattr__(self, "timespan", timedelta(milliseconds=self.timespan))

    def to_dict(self) -> dict[str, Any]:
        p = _PRICE_PRECISION.get(self.symbol.asset_type, 6)
        return {
            "symbol": self.symbol.to_dict(),
            "date_open": self.date_open.isoformat(),
            "open": round(self.open, p),
            "high": round(self.high, p),
            "low": round(self.low, p),
            "close": round(self.close, p),
            "volume": round(self.volume, 2),
            "timespan_sec": round(self.timespan.total_seconds()),
        }

    @property
    def timespan_ms(self) -> int:
        """Timespan in milliseconds."""
        return int(self.timespan.total_seconds() * 1000)

    @property
    def date_close(self) -> datetime:
        """End of the period (date_open + timespan)."""
        return self.date_open + self.timespan


@dataclass
class DailyOpenCloseAggregate(OHLCV):
    """Daily OHLCV aggregate enriched with pre-market and after-hours prices.

    close may be None during an active session (Polygon omits it until the day ends).
    """
    close: float | None  # type: ignore[assignment]  # override base; None during active session
    pre_market: float | None
    after_hours: float | None

    def to_dict(self) -> dict[str, Any]:
        p = _PRICE_PRECISION.get(self.symbol.asset_type, 6)
        d: dict[str, Any] = {
            "symbol": self.symbol.to_dict(),
            "date": self.date_open.date().isoformat(),
            "open": round(self.open, p),
            "high": round(self.high, p),
            "low": round(self.low, p),
            "close": round(self.close, p) if self.close is not None else None,
            "volume": round(self.volume, 2),
            "pre_market": round(self.pre_market, p) if self.pre_market is not None else None,
            "after_hours": round(self.after_hours, p) if self.after_hours is not None else None,
        }
        return d


class SymbolMemoryCache[T: OHLCV]:
    """Generic per-symbol in-memory time-series cache.

    Entries are stored in a SortedDict keyed by timestamp_ms and evicted
    automatically once they age past max_age.
    """

    def __init__(self, max_age: timedelta) -> None:
        self._max_age: timedelta = max_age
        self._data: dict[AssetSymbol, SortedDict] = {}

    @property
    def max_age(self) -> timedelta:
        return self._max_age

    def add(self, item: T) -> None:
        """Add an item, evicting entries older than max_age for that symbol."""
        symbol = item.symbol
        if symbol not in self._data:
            self._data[symbol] = SortedDict()
        self._data[symbol][item.timestamp_ms] = item
        self._evict(symbol)

    def _evict(self, symbol: AssetSymbol) -> None:
        """Remove all entries for symbol older than max_age."""
        cutoff_ms = ms_from_datetime(datetime.now(ZoneInfo("UTC")) - self._max_age)
        cache = self._data[symbol]
        while cache and cache.peekitem(0)[0] < cutoff_ms:
            cache.popitem(0)
        if not cache:
            del self._data[symbol]

    def get_latest(self, symbol: AssetSymbol) -> T | None:
        """Return the most recent entry for symbol, or None."""
        if symbol not in self._data:
            return None
        return self._data[symbol].peekitem(-1)[1]

    def get_range(self, symbol: AssetSymbol, from_: datetime, to: datetime) -> list[T]:
        """Return all entries for symbol within [from_, to] inclusive."""
        if symbol not in self._data:
            return []
        from_ms = ms_from_datetime(from_)
        to_ms = ms_from_datetime(to)
        cache = self._data[symbol]
        return [cache[ts_ms] for ts_ms in cache.irange(from_ms, to_ms)]

    def get_at(self, symbol: AssetSymbol, timestamp_ms: int) -> T | None:
        """Return the entry at an exact timestamp_ms key, or None."""
        if symbol not in self._data:
            return None
        return self._data[symbol].get(timestamp_ms)


def _eastern_midnight_ms(dt: datetime) -> int:
    """Return epoch milliseconds for midnight Eastern on the Eastern calendar date of dt."""
    eastern = dt.astimezone(ZoneInfo("America/New_York"))
    midnight = datetime(eastern.year, eastern.month, eastern.day, tzinfo=ZoneInfo("America/New_York"))
    return ms_from_datetime(midnight)


class AggregateCache:
    def __init__(self, cache_file: Path | str | None):
        self._cache_file: Path | None = Path(cache_file) if cache_file is not None else None

        self._minute_cache: SymbolMemoryCache[Aggregate] = SymbolMemoryCache(timedelta(days=7))
        self._daily_cache: SymbolMemoryCache[DailyOpenCloseAggregate] = SymbolMemoryCache(timedelta(days=30))

        self._is_initialized: bool = False

        self._spawn_lock: asyncio.Lock = asyncio.Lock()
        self._process_lock: asyncio.Lock = asyncio.Lock()
        self._update_in_progress: asyncio.Event = asyncio.Event()
        self._pending_minute_updates: asyncio.Queue[Aggregate] = asyncio.Queue()
        self._pending_daily_updates: asyncio.Queue[DailyOpenCloseAggregate] = asyncio.Queue()
        self._background_tasks: set = set()

    def initialize(self) -> None:
        """Initialize the SQLite database, or no-op for memory-only mode."""
        if self._cache_file is not None:
            self._init_db()
        self._is_initialized = True

    def _init_db(self) -> None:
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='info'"
            )
            table_exists = cursor.fetchone() is not None

            current_version = 0
            if table_exists:
                cursor.execute("SELECT value FROM info WHERE key='schema_version'")
                result = cursor.fetchone()
                if result:
                    current_version = int(result[0])

            self._run_migrations(conn, current_version)
            conn.commit()

    def _run_migrations(self, conn: sqlite3.Connection, current_version: int) -> None:
        migrations = {
            1: self._migrate_to_v1,
            2: self._migrate_to_v2,
            3: self._migrate_to_v3,
            4: self._migrate_to_v4,
        }

        for version in sorted([v for v in migrations.keys() if v > current_version]):
            logger.info(f"Migrating database schema to version {version}")
            migrations[version](conn)

            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO info (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", str(version), datetime.now().isoformat()),
            )
            conn.commit()

    def _migrate_to_v1(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()

        # Create info table for key-value pairs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS info (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table of aggregate data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aggregates (
                symbol TEXT,
                date_utc INTEGER,  -- Store as milliseconds since epoch
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (symbol, date_utc)
            )
        """)

        # Create index for efficient range queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_symbol_date
            ON aggregates(symbol, date_utc)
        """)

        # Index for time-based queries across all symbols
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_date_utc
            ON aggregates(date_utc)
        """)

    def _migrate_to_v2(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                asset_type TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _migrate_to_v3(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE aggregates ADD COLUMN timespan_ms INTEGER")
        cursor.execute("ALTER TABLE aggregates ADD COLUMN asset_type TEXT")
        # Backfill from existing data
        cursor.execute(
            "UPDATE aggregates SET timespan_ms = 60000 WHERE timespan_ms IS NULL"
        )
        cursor.execute("""
            UPDATE aggregates
            SET asset_type = (SELECT s.asset_type FROM symbols s WHERE s.symbol = aggregates.symbol)
            WHERE asset_type IS NULL
        """)

    def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aggregates_open_close (
                symbol TEXT,
                asset_type TEXT,
                date_utc INTEGER,  -- milliseconds since epoch (midnight Eastern of the trading day)
                open REAL,
                high REAL,
                low REAL,
                close REAL,        -- NULL during active session
                volume REAL,
                pre_market REAL,   -- NULL if unavailable
                after_hours REAL,  -- NULL if unavailable
                PRIMARY KEY (symbol, date_utc)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_open_close_symbol_date
            ON aggregates_open_close(symbol, date_utc)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_open_close_date_utc
            ON aggregates_open_close(date_utc)
        """)

    async def wait_for_completion(self) -> None:
        """Wait for all pending updates to be written to the database."""
        task = None
        # If there are pending updates and no processing is happening, start it
        async with self._spawn_lock:
            if (
                (not self._pending_minute_updates.empty() or not self._pending_daily_updates.empty())
                and not self._update_in_progress.is_set()
            ):
                self._update_in_progress.set()
                task = asyncio.create_task(
                    self._process_updates(),
                    context=contextvars.Context(),
                )
                # We'll wait for it below

        # Wait until the queue is empty and processing is complete
        while (
            not self._pending_minute_updates.empty()
            or not self._pending_daily_updates.empty()
            or self._update_in_progress.is_set()
        ):
            try:
                await asyncio.sleep(0.1)  # Small sleep to avoid busy waiting
            except asyncio.CancelledError:
                break

        if task:
            await task

    async def close(self) -> None:
        """Close the cache and ensure all pending updates are written."""
        logger.info("Closing AggregateCache...")

        # Wait for all pending updates to be processed
        await self.wait_for_completion()

        # Cancel any remaining background tasks
        for task in self._background_tasks:
            if not task.done():
                logger.debug(f"Cancelling background task: {task.get_name()}")
                task.cancel()

        # Wait for all tasks to complete
        if self._background_tasks:
            done, pending = await asyncio.wait(self._background_tasks, timeout=5)
            if pending:
                logger.warning(
                    f"Some background tasks did not complete: {len(pending)}"
                )

        logger.info("AggregateCache closed successfully")

    @logfire.instrument("cache.load")
    async def load(self) -> "AggregateCache":
        """Load recent aggregates from SQLite into the in-memory caches."""
        if not self._is_initialized:
            self.initialize()

        if self._cache_file is None:
            return self

        assert self._cache_file.exists(), (
            f"Cache file: {self._cache_file} does not exist"
        )

        logger.info(f"Loading aggregates from {self._cache_file}")
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()

            # Load minute aggregates
            cutoff_ms = ms_from_datetime(
                datetime.now(ZoneInfo("UTC")) - self._minute_cache.max_age
            )
            cursor.execute(
                """SELECT a.symbol, a.date_utc, a.open, a.high, a.low, a.close,
                          a.volume, a.timespan_ms, a.asset_type
                   FROM aggregates a
                   WHERE a.date_utc >= ?""",
                (cutoff_ms,),
            )
            minute_rows = cursor.fetchall()
            logfire_set_attribute("minute_row_count", len(minute_rows))
            for ticker, date_utc_ms, open_, high, low, close, volume, timespan_ms, asset_type in minute_rows:
                date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
                symbol = AssetSymbol(ticker, AssetTypes(asset_type))
                self._minute_cache.add(
                    Aggregate(symbol, date, open_, high, low, close, volume, timedelta(milliseconds=timespan_ms))
                )

            # Load daily open-close aggregates
            cutoff_ms = ms_from_datetime(
                datetime.now(ZoneInfo("UTC")) - self._daily_cache.max_age
            )
            cursor.execute(
                """SELECT symbol, asset_type, date_utc, open, high, low, close,
                          volume, pre_market, after_hours
                   FROM aggregates_open_close
                   WHERE date_utc >= ?""",
                (cutoff_ms,),
            )
            daily_rows = cursor.fetchall()
            logfire_set_attribute("daily_row_count", len(daily_rows))
            for ticker, asset_type, date_utc_ms, open_, high, low, close, volume, pre_market, after_hours in daily_rows:
                date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
                symbol = AssetSymbol(ticker, AssetTypes(asset_type))
                self._daily_cache.add(DailyOpenCloseAggregate(
                    symbol=symbol,
                    date_open=date,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    pre_market=pre_market,
                    after_hours=after_hours,
                ))

        return self

    async def _maybe_spawn_update_task(self) -> None:
        """Spawn a background task to drain pending queues if one is not already running."""
        async with self._spawn_lock:
            if not self._update_in_progress.is_set():
                # Set synchronously under the lock so concurrent callers
                # reaching this point before the task starts don't spawn a second one.
                self._update_in_progress.set()
                task = asyncio.create_task(
                    self._process_updates(),
                    context=contextvars.Context(),
                )
                task.set_name(f"AggregateCache._process_updates-{id(task)}")
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

    async def _process_updates(self) -> None:
        """Drain both pending queues to SQLite."""
        async with self._process_lock:
            try:
                batch_size = 100
                total_written = 0
                batches = 0

                with logfire.span("cache.flush"):
                    while (
                        not self._pending_minute_updates.empty()
                        or not self._pending_daily_updates.empty()
                    ):
                        # Minute batch
                        minute_batch: list[Aggregate] = []
                        while len(minute_batch) < batch_size:
                            try:
                                minute_batch.append(self._pending_minute_updates.get_nowait())
                            except asyncio.QueueEmpty:
                                break

                        if minute_batch:
                            try:
                                with logfire.span("cache.db_write", batch_size=len(minute_batch)):
                                    await asyncio.to_thread(self._write_minute_batch, minute_batch)
                                total_written += len(minute_batch)
                                batches += 1
                            except asyncio.CancelledError:
                                logger.warning(
                                    "Processing was cancelled, committing current batch before exit"
                                )
                                raise

                        # Daily batch
                        daily_batch: list[DailyOpenCloseAggregate] = []
                        while len(daily_batch) < batch_size:
                            try:
                                daily_batch.append(self._pending_daily_updates.get_nowait())
                            except asyncio.QueueEmpty:
                                break

                        if daily_batch:
                            try:
                                with logfire.span("cache.db_write_daily", batch_size=len(daily_batch)):
                                    await asyncio.to_thread(self._write_daily_batch, daily_batch)
                                total_written += len(daily_batch)
                                batches += 1
                            except asyncio.CancelledError:
                                logger.warning(
                                    "Processing was cancelled, committing current daily batch before exit"
                                )
                                raise

                        await asyncio.sleep(0)

                    logfire_set_attribute("total_written", total_written)
                    logfire_set_attribute("batch_count", batches)

            except Exception as e:
                logger.error(f"Error processing updates: {e}")
                raise
            finally:
                self._update_in_progress.clear()

    async def add(self, aggregate: Aggregate) -> None:
        """Add a minute aggregate to the in-memory cache and queue for SQLite persistence."""
        self._minute_cache.add(aggregate)
        if self._cache_file is not None:
            await self._pending_minute_updates.put(aggregate)
            await self._maybe_spawn_update_task()

    async def add_open_close(self, aggregate: DailyOpenCloseAggregate) -> None:
        """Add a daily open-close aggregate to the in-memory cache and queue for SQLite persistence."""
        self._daily_cache.add(aggregate)
        if self._cache_file is not None:
            await self._pending_daily_updates.put(aggregate)
            await self._maybe_spawn_update_task()

    def _write_minute_batch(self, aggregates: list[Aggregate]) -> None:
        """Write a batch of minute aggregates to SQLite (runs in a thread)."""
        if not aggregates:
            return
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT OR REPLACE INTO aggregates
                   (symbol, date_utc, open, high, low, close, volume, timespan_ms, asset_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        agg.symbol.ticker,
                        agg.timestamp_ms,
                        agg.open,
                        agg.high,
                        agg.low,
                        agg.close,
                        agg.volume,
                        agg.timespan_ms,
                        agg.symbol.asset_type.value,
                    )
                    for agg in aggregates
                ],
            )
            cursor.executemany(
                "INSERT OR REPLACE INTO symbols (symbol, asset_type) VALUES (?, ?)",
                [
                    (agg.symbol.ticker, agg.symbol.asset_type.value)
                    for agg in aggregates
                ],
            )
            conn.commit()

    def _write_daily_batch(self, aggregates: list[DailyOpenCloseAggregate]) -> None:
        """Write a batch of daily open-close aggregates to SQLite (runs in a thread)."""
        if not aggregates:
            return
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT OR REPLACE INTO aggregates_open_close
                   (symbol, asset_type, date_utc, open, high, low, close, volume, pre_market, after_hours)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        agg.symbol.ticker,
                        agg.symbol.asset_type.value,
                        agg.timestamp_ms,
                        agg.open,
                        agg.high,
                        agg.low,
                        agg.close,
                        agg.volume,
                        agg.pre_market,
                        agg.after_hours,
                    )
                    for agg in aggregates
                ],
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # Sync read (memory only)
    # -------------------------------------------------------------------------

    @logfire.instrument("cache.get_range {symbol.ticker}")
    def get_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[Aggregate]:
        """Return cached minute aggregates for symbol within [from_, to] inclusive.

        Memory-only; does not fall back to SQLite.
        """
        result = self._minute_cache.get_range(symbol, from_, to)
        logfire_set_attribute("result_count", len(result))
        return result

    # -------------------------------------------------------------------------
    # Async reads (memory → SQLite fallback)
    # -------------------------------------------------------------------------

    @logfire.instrument("cache.get_current {symbol.ticker}")
    async def get_current(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the most recent minute aggregate from the in-memory cache."""
        return self._minute_cache.get_latest(symbol)

    @logfire.instrument("cache.get_close {symbol.ticker}")
    async def get_close(self, symbol: AssetSymbol, date: datetime) -> Aggregate | None:
        """Return the aggregate for the trading session closing on date.

        Checks the session window in memory first, then falls back to SQLite.
        """
        close_time = MarketInfo.get_market_close(symbol, date)
        session_start = close_time.replace(hour=0, minute=0, second=0, microsecond=0)
        aggregates = self._minute_cache.get_range(symbol, session_start, close_time)
        if aggregates:
            logfire_set_attribute("source", "memory")
            return aggregates[-1]
        if self._cache_file is None:
            return None
        logfire_set_attribute("source", "db")
        return await asyncio.to_thread(self._db_get_session_close, symbol, session_start, close_time)

    @logfire.instrument("cache.get_open_close {symbol.ticker}")
    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None
    ) -> DailyOpenCloseAggregate | None:
        """Return the daily open-close aggregate for the given date.

        Keyed by Eastern midnight of the trading day. Checks memory then SQLite.
        """
        target = date or datetime.now(ZoneInfo("UTC"))
        target_ms = _eastern_midnight_ms(target)

        result = self._daily_cache.get_at(symbol, target_ms)
        if result is not None:
            logfire_set_attribute("source", "memory")
            return result
        if self._cache_file is None:
            return None
        logfire_set_attribute("source", "db")
        return await asyncio.to_thread(self._db_get_open_close, symbol, target_ms)

    @logfire.instrument("cache.get_open_close_range {symbol.ticker}")
    async def get_open_close_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[DailyOpenCloseAggregate]:
        """Return daily open-close aggregates for symbol within [from_, to] inclusive.

        Checks memory first, then falls back to SQLite.
        """
        results = self._daily_cache.get_range(symbol, from_, to)
        if results:
            logfire_set_attribute("source", "memory")
            return results
        if self._cache_file is None:
            return []
        logfire_set_attribute("source", "db")
        return await asyncio.to_thread(self._db_get_open_close_range, symbol, from_, to)

    # -------------------------------------------------------------------------
    # SQLite read helpers (sync; always run via asyncio.to_thread)
    # -------------------------------------------------------------------------

    def _db_get_session_close(
        self, symbol: AssetSymbol, session_start: datetime, close_time: datetime
    ) -> Aggregate | None:
        if self._cache_file is None:
            return None
        start_ms = ms_from_datetime(session_start)
        end_ms = ms_from_datetime(close_time)
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT date_utc, open, high, low, close, volume, timespan_ms, asset_type
                   FROM aggregates
                   WHERE symbol = ? AND date_utc >= ? AND date_utc <= ?
                   ORDER BY date_utc DESC LIMIT 1""",
                (symbol.ticker, start_ms, end_ms),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        date_utc_ms, open_, high, low, close, volume, timespan_ms, asset_type = row
        date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
        resolved = AssetSymbol(symbol.ticker, AssetTypes(asset_type)) if asset_type else symbol
        return Aggregate(resolved, date, open_, high, low, close, volume, timedelta(milliseconds=timespan_ms))

    def _db_get_open_close(
        self, symbol: AssetSymbol, date_utc_ms: int
    ) -> DailyOpenCloseAggregate | None:
        if self._cache_file is None:
            return None
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT date_utc, open, high, low, close, volume, pre_market, after_hours, asset_type
                   FROM aggregates_open_close
                   WHERE symbol = ? AND date_utc = ?""",
                (symbol.ticker, date_utc_ms),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        date_utc_ms_, open_, high, low, close, volume, pre_market, after_hours, asset_type = row
        date = datetime_from_ms(date_utc_ms_, ZoneInfo("UTC"))
        resolved = AssetSymbol(symbol.ticker, AssetTypes(asset_type)) if asset_type else symbol
        return DailyOpenCloseAggregate(
            symbol=resolved,
            date_open=date,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            pre_market=pre_market,
            after_hours=after_hours,
        )


    def _db_get_open_close_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[DailyOpenCloseAggregate]:
        start_ms = ms_from_datetime(from_)
        end_ms = ms_from_datetime(to)
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT date_utc, open, high, low, close, volume, pre_market, after_hours, asset_type
                   FROM aggregates_open_close
                   WHERE symbol = ? AND date_utc >= ? AND date_utc <= ?
                   ORDER BY date_utc ASC""",
                (symbol.ticker, start_ms, end_ms),
            )
            rows = cursor.fetchall()
        result = []
        for date_utc_ms, open_, high, low, close, volume, pre_market, after_hours, asset_type in rows:
            date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
            resolved = AssetSymbol(symbol.ticker, AssetTypes(asset_type)) if asset_type else symbol
            result.append(DailyOpenCloseAggregate(
                symbol=resolved,
                date_open=date,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                pre_market=pre_market,
                after_hours=after_hours,
            ))
        return result


class MemoryOnlyAggregateCache(AggregateCache):
    """In-memory-only cache that skips all SQLite persistence."""

    def __init__(self) -> None:
        super().__init__(cache_file=None)
