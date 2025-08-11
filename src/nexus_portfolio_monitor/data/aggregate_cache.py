import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sqlite3

from sortedcontainers import SortedDict

SymbolT = str

logger = logging.getLogger(__name__)

@dataclass
class Aggregate:
    symbol: SymbolT
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

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
        self._memory_cache: dict[SymbolT, SortedDict] = {}

        self._spawn_lock = asyncio.Lock()    # Guards task spawning logic
        self._process_lock = asyncio.Lock()  # Ensures _process_updates runs exclusively
        self._update_in_progress = asyncio.Event()
        self._pending_db_updates: asyncio.Queue[Aggregate] = asyncio.Queue()

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
                date INTEGER,  -- Store as milliseconds since epoch
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (symbol, date)
            )
        """)
            
        # Create index for efficient range queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_symbol_date 
            ON aggregates(symbol, date)
        """)
        
        # Index for time-based queries across all symbols
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggregates_date 
            ON aggregates(date)
        """)
        
    async def wait_for_completion(self):
        """Wait for all pending updates to be written to database"""
        # Just wait until queue is empty and processing is done
        while not self._pending_db_updates.empty() or self._update_in_progress.is_set():
            await asyncio.sleep(0.01)
    
    async def load(self):
        """
        Load the cache from an sqlite database
        """
        if not self._is_initialized:
            self.initialize()

        assert self._cache_file.exists(), f"Cache file: {self._cache_file} does not exist"

        with sqlite3.connect(self._cache_file) as conn:
            cursor = conn.cursor()
            
            cache_time_ms = ms_from_datetime(datetime.now() - self._memory_cache_age)
            cursor.execute(
                "SELECT * FROM aggregates WHERE date >= ?",
                (cache_time_ms,)
            )

            rows = cursor.fetchall()
            for row in rows:
                symbol: SymbolT = row[0]
                date_ms: int = row[1]
                open: float = row[2]
                high: float = row[3]
                low: float = row[4]
                close: float = row[5]
                volume: int = row[6]

                date = datetime_from_ms(date_ms)
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
                        await asyncio.to_thread(self._add_batch_to_db, batch)
                    
                    # Always yield after each batch for responsiveness
                    await asyncio.sleep(0)
                    
            finally:
                self._update_in_progress.clear()

    async def add(self, aggregate: Aggregate):
        """Add an aggregate to the cache and queue it for database persistence"""
        self._add_to_memory_cache(aggregate)
        await self._pending_db_updates.put(aggregate)
        
        # Spawn a task to process updates if needed
        async with self._spawn_lock:  # Use spawn_lock to guard task creation
            if not self._update_in_progress.is_set():
                asyncio.create_task(self._process_updates())

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
                "INSERT OR REPLACE INTO aggregates (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (agg.symbol, agg.timestamp_ms, agg.open, agg.high, agg.low, agg.close, agg.volume)
                    for agg in aggregates
                ]
            )
            conn.commit()

    def get_current(self, symbol: SymbolT) -> Aggregate | None:
        if symbol not in self._memory_cache:
            return None
        return self._memory_cache[symbol].peekitem(-1)[1]

def datetime_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000)

def ms_from_datetime(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
