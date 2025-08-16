import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from sortedcontainers import SortedDict
from nexus_portfolio_monitor.service.types import AssetSymbol, AssetTypes

logger = logging.getLogger(__name__)

@dataclass
class Aggregate:
    symbol: AssetSymbol
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def __post_init__(self):
        """Validate that the date is timezone-aware"""
        if self.date.tzinfo is None:
            raise ValueError(f"Aggregate date must be timezone-aware. Got: {self.date}")

    @property
    def timestamp_ms(self) -> int:
        """Convert datetime to milliseconds since epoch"""
        return int(self.date.timestamp() * 1000)

class AggregateCache:
    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, cache_file: Path | str):
        self._cache_file = Path(cache_file)
        self._memory_cache_age = timedelta(days=7)

        self._is_initialized = False
        self._memory_cache: dict[AssetSymbol, SortedDict] = {}

        self._spawn_lock = asyncio.Lock()    # Guards task spawning logic
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
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='info'")
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
        }
        
        # Apply migrations in version order
        for version in sorted([v for v in migrations.keys() if v > current_version]):
            logger.info(f"Migrating database schema to version {version}")
            migrations[version](conn)
            
            # Update schema version
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO info (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", str(version), datetime.now().isoformat())
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
        
    async def wait_for_completion(self):
        """Wait for all pending updates to be written to database"""
        task = None
        # If there are pending updates and no processing is happening, start it
        async with self._spawn_lock:
            if not self._pending_db_updates.empty() and not self._update_in_progress.is_set():
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
        logger.info("Closing AggregateCache and ensuring all updates are written...")
        
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
                logger.warning(f"Some background tasks did not complete: {len(pending)}")
            
        logger.info("AggregateCache closed successfully")
    
    async def load(self):
        """
        Load the cache from an sqlite database
        """
        if not self._is_initialized:
            self.initialize()
            
        assert self._cache_file.exists(), f"Cache file: {self._cache_file} does not exist"
            
        logger.info(f"Loading aggregates from {self._cache_file}") 
        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            
            utc_time_ms = ms_from_datetime(datetime.now(ZoneInfo("UTC")) - self._memory_cache_age)
            cursor.execute(
                """SELECT aggregates.*, symbols.asset_type 
                FROM aggregates JOIN symbols ON aggregates.symbol = symbols.symbol 
                WHERE aggregates.date_utc >= ?""",
                (utc_time_ms,)
            )

            rows = cursor.fetchall()
            for row in rows:
                ticker: str = row[0]
                date_utc_ms: int = row[1]
                open: float = row[2]
                high: float = row[3]
                low: float = row[4]
                close: float = row[5]
                volume: int = row[6]
                asset_type: str = row[7]

                date = datetime_from_ms(date_utc_ms, ZoneInfo("UTC"))
                symbol = AssetSymbol(ticker, AssetTypes(asset_type))
                aggregate = Aggregate(symbol, date, open, high, low, close, volume)
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
                            logger.warning("Processing was cancelled, committing current batch before exit")
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
                "INSERT OR REPLACE INTO aggregates (symbol, date_utc, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (agg.symbol.ticker, agg.timestamp_ms, agg.open, agg.high, agg.low, agg.close, agg.volume)
                    for agg in aggregates
                ]
            )
            cursor.executemany(
                "INSERT OR REPLACE INTO symbols (symbol, asset_type) VALUES (?, ?)",
                [
                    (agg.symbol.ticker, agg.symbol.asset_type.value)
                    for agg in aggregates
                ]
            )
            conn.commit()

    def get_current(self, symbol: AssetSymbol) -> Aggregate | None:
        if symbol not in self._memory_cache:
            return None
        return self._memory_cache[symbol].peekitem(-1)[1]

def datetime_from_ms(ms: int, tz: ZoneInfo) -> datetime:
    assert tz is not None, "Timezone must be specified"
    return datetime.fromtimestamp(ms / 1000, tz)

def ms_from_datetime(dt: datetime) -> int:
    """
    Convert datetime to milliseconds since epoch, ensuring datetime is timezone aware
    and converting to UTC first.
    """
    if dt.tzinfo is None:
        raise ValueError(f"Datetime must be timezone-aware. Got: {dt}")
    
    # Convert to UTC if not already
    utc_dt = dt.astimezone(ZoneInfo("UTC"))
    return int(utc_dt.timestamp() * 1000)
