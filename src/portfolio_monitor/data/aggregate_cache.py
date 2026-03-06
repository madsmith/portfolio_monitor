import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo

from sortedcontainers import SortedDict

from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.utils.time import datetime_from_ms, ms_from_datetime

# Price decimal places by asset type for JSON serialization
_PRICE_PRECISION: dict[AssetTypes, int] = {
    AssetTypes.Stock: 2,
    AssetTypes.Currency: 4,
    AssetTypes.Crypto: 6,
}

logger = logging.getLogger(__name__)


@dataclass
class Aggregate:
    symbol: AssetSymbol
    date_open: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timespan: timedelta

    def __post_init__(self):
        """Validate and coerce fields."""
        if not isinstance(self.symbol, AssetSymbol):
            raise TypeError(
                f"symbol must be an AssetSymbol, got {type(self.symbol).__name__}: {self.symbol!r}"
            )
        if self.date_open.tzinfo is None:
            raise ValueError(
                f"Aggregate date_open must be timezone-aware. Got: {self.date_open}"
            )
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
    def timestamp_ms(self) -> int:
        """Convert datetime to milliseconds since epoch"""
        return int(self.date_open.timestamp() * 1000)

    @property
    def timespan_ms(self) -> int:
        """Convert timespan to milliseconds"""
        return int(self.timespan.total_seconds() * 1000)


class AggregateCache:
    def __init__(self, cache_file: Path | str):
        self._cache_file = Path(cache_file)
        self._memory_cache_age = timedelta(days=7)

        self._is_initialized = False
        self._memory_cache: dict[AssetSymbol, SortedDict] = {}

        self._spawn_lock = asyncio.Lock()  # Guards task spawning logic
        self._process_lock = asyncio.Lock()  # Ensures _process_updates runs exclusively
        self._update_in_progress = asyncio.Event()
        self._pending_db_updates: asyncio.Queue[Aggregate] = asyncio.Queue()
        self._background_tasks = set()  # Track background tasks for cleanup

    def set_memory_cache_age(self, age: timedelta):
        """
        Set the age of the in memory cache
        """
        assert isinstance(age, timedelta), "Age must be a timedelta"
        assert age.total_seconds() > 0, "Age must be greater than 0"

        self._memory_cache_age = age

    def initialize(self):
        """
        Initialize the sqlite database
        """
        self._init_db()
        self._is_initialized = True

    def _init_db(self):
        """
        Initialize the sqlite database
        """
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()

            # Check if the info table exists to determine current schema version
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='info'"
            )
            table_exists = cursor.fetchone() is not None

            current_version = 0
            if table_exists:
                # Get current schema version from the info table
                cursor.execute("SELECT value FROM info WHERE key='schema_version'")
                result = cursor.fetchone()
                if result:
                    current_version = int(result[0])

            # Run all necessary migrations in sequence
            self._run_migrations(conn, current_version)

            conn.commit()

    def _run_migrations(self, conn: sqlite3.Connection, current_version: int):
        """
        Run migrations sequentially to update the database schema.

        Args:
            conn: SQLite connection
            current_version: Current schema version of the database
        """
        # Dictionary of migration functions keyed by target version
        migrations = {
            1: self._migrate_to_v1,
            2: self._migrate_to_v2,
            3: self._migrate_to_v3,
        }

        # Apply migrations in version order
        for version in sorted([v for v in migrations.keys() if v > current_version]):
            logger.info(f"Migrating database schema to version {version}")
            migrations[version](conn)

            # Update schema version
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO info (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", str(version), datetime.now().isoformat()),
            )
            conn.commit()

    def _migrate_to_v1(self, conn: sqlite3.Connection):
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

    def _migrate_to_v2(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                asset_type TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _migrate_to_v3(self, conn: sqlite3.Connection):
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

    async def wait_for_completion(self):
        """Wait for all pending updates to be written to database"""
        task = None
        # If there are pending updates and no processing is happening, start it
        async with self._spawn_lock:
            if (
                not self._pending_db_updates.empty()
                and not self._update_in_progress.is_set()
            ):
                task = asyncio.create_task(self._process_updates())
                # We'll wait for it below

        # Wait until the queue is empty and processing is complete
        while not self._pending_db_updates.empty() or self._update_in_progress.is_set():
            try:
                await asyncio.sleep(0.1)  # Small sleep to avoid busy waiting
            except asyncio.CancelledError:
                break

        if task:
            await task

    async def close(self):
        """Close the cache and ensure all pending updates are written"""
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

    async def load(self):
        """
        Load the cache from an sqlite database
        """
        if not self._is_initialized:
            self.initialize()

        assert self._cache_file.exists(), (
            f"Cache file: {self._cache_file} does not exist"
        )

        logger.info(f"Loading aggregates from {self._cache_file}")
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()

            utc_time_ms = ms_from_datetime(
                datetime.now(ZoneInfo("UTC")) - self._memory_cache_age
            )
            cursor.execute(
                """SELECT
                    a.symbol,
                    a.date_utc,
                    a.open,
                    a.high,
                    a.low,
                    a.close,
                    a.volume,
                    a.timespan_ms,
                    a.asset_type
                FROM aggregates a
                WHERE a.date_utc >= ?""",
                (utc_time_ms,),
            )

            rows = cursor.fetchall()
            for (
                ticker,
                date_utc_ms,
                open_,
                high,
                low,
                close,
                volume,
                timespan_ms,
                asset_type,
            ) in rows:
                date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
                timespan = timedelta(milliseconds=timespan_ms)
                symbol = AssetSymbol(ticker, AssetTypes(asset_type))
                aggregate = Aggregate(
                    symbol, date, open_, high, low, close, volume, timespan
                )
                await self.add(aggregate)

        return self

    async def _process_updates(self):
        """Process pending updates with periodic yielding"""
        async with self._process_lock:
            self._update_in_progress.set()
            try:
                batch_size = 100

                while not self._pending_db_updates.empty():
                    batch = []

                    # Get a batch
                    while len(batch) < batch_size:
                        try:
                            batch.append(self._pending_db_updates.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    if batch:
                        try:
                            await asyncio.to_thread(self._add_batch_to_db, batch)
                        except asyncio.CancelledError:
                            logger.warning(
                                "Processing was cancelled, committing current batch before exit"
                            )
                            raise

                    # Always yield after each batch for responsiveness
                    await asyncio.sleep(0)

            except Exception as e:
                logger.error(f"Error processing updates: {e}")
                raise
            finally:
                self._update_in_progress.clear()

    async def add(self, aggregate: Aggregate):
        """Add an aggregate to the cache and queue it for database persistence"""
        self._add_to_memory_cache(aggregate)
        await self._pending_db_updates.put(aggregate)

        # Spawn a task to process updates if needed
        async with self._spawn_lock:  # Use spawn_lock to guard task creation
            if not self._update_in_progress.is_set():
                task = asyncio.create_task(self._process_updates())
                # Name the task for debugging
                task.set_name(f"AggregateCache._process_updates-{id(task)}")
                # Track the task for cleanup
                self._background_tasks.add(task)

                # Set up callback to remove task from set when done
                def _remove_task(t):
                    self._background_tasks.discard(t)

                task.add_done_callback(_remove_task)

    def _add_to_memory_cache(self, aggregate: Aggregate):
        if aggregate.symbol not in self._memory_cache:
            self._memory_cache[aggregate.symbol] = SortedDict()
        self._memory_cache[aggregate.symbol][aggregate.timestamp_ms] = aggregate

    def _add_batch_to_db(self, aggregates: list[Aggregate]):
        """Add multiple aggregates to the database in a single transaction"""
        if not aggregates:
            return

        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO aggregates (
                    symbol, date_utc, open, high, low, close, volume, timespan_ms, asset_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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

    def get_current(self, symbol: AssetSymbol) -> Aggregate | None:
        if symbol not in self._memory_cache:
            return None
        return self._memory_cache[symbol].peekitem(-1)[1]

    def get_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[Aggregate]:
        """
        Return cached aggregates for *symbol* within [from_, to] inclusive.
        """
        if symbol not in self._memory_cache:
            return []

        from_ms = ms_from_datetime(from_)
        to_ms = ms_from_datetime(to)
        cache = self._memory_cache[symbol]

        return [cache[ts_ms] for ts_ms in cache.irange(from_ms, to_ms)]

    def get_close(self, symbol: AssetSymbol, date: datetime) -> "Aggregate | None":
        """Return the cached aggregate for the trading session that closes on *date*.

        Searches the range [midnight UTC on the close day, market close time] and
        returns the last aggregate found.  Returns None if nothing is cached for
        that session.
        """
        close_time = MarketInfo.get_market_close(symbol, date)
        # Session window: midnight UTC on the close day → close_time
        session_start = close_time.replace(hour=0, minute=0, second=0, microsecond=0)
        aggregates = self.get_range(symbol, session_start, close_time)
        return aggregates[-1] if aggregates else None


class MemoryOnlyAggregateCache(AggregateCache):
    """In-memory-only cache that skips all SQLite persistence."""

    def __init__(self) -> None:
        self._memory_cache_age = timedelta(days=7)
        self._is_initialized = True
        self._memory_cache: dict[AssetSymbol, SortedDict] = {}

    def initialize(self) -> None:
        pass

    async def load(self) -> "MemoryOnlyAggregateCache":
        return self

    async def add(self, aggregate: Aggregate) -> None:
        self._add_to_memory_cache(aggregate)

    async def close(self) -> None:
        pass
