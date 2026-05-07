import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class MigrationStep:
    """A single versioned migration belonging to a module.

    ``version`` is the version the module reaches after this step runs.
    ``apply`` performs the schema change.
    ``requires`` lists (module_name, min_version) pairs that must already be
    satisfied before this step can run — enabling cross-module ordering.
    """

    version: int
    apply: Callable[[sqlite3.Connection], None]
    requires: list[tuple[str, int]] = field(default_factory=list)


class DatabaseModule(ABC):
    """Base class for a self-contained schema+CRUD unit within the Database.

    Subclasses declare their migration history as an ordered list of
    MigrationStep objects. The Database scheduler runs steps in version order
    within each module and respects cross-module ``requires`` declarations.
    """

    name: str

    def bind(self, conn: sqlite3.Connection) -> None:
        self._conn: sqlite3.Connection = conn

    @property
    @abstractmethod
    def migrations(self) -> list[MigrationStep]: ...


class Database:
    """SQLite database with independently versioned, dependency-aware modules.

    On initialize(), collects every MigrationStep from every DatabaseModule and
    runs a dependency-ordered scheduler: within each module steps run in
    ascending version order; cross-module ``requires`` constraints are satisfied
    before a step fires. Raises RuntimeError if a deadlock is detected.
    """

    def __init__(self, path: Path, modules: list[DatabaseModule]) -> None:
        self._path: Path = path
        self._modules: list[DatabaseModule] = modules
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_info_table()
        for module in self._modules:
            module.bind(self._conn)
        self._run_migrations()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Migration scheduler
    # ------------------------------------------------------------------

    def _run_migrations(self) -> None:
        total_steps = sum(len(m.migrations) for m in self._modules)
        for _ in range(total_steps + 1):
            step_ran = self._run_next_step()
            if not step_ran:
                # No step ran — either all done or a deadlock
                pending = self._pending_steps()
                if pending:
                    raise RuntimeError(
                        f"Migration deadlock — unresolvable dependencies: {pending}"
                    )
                return

    def _run_next_step(self) -> bool:
        """Find and run the lowest-version pending step whose deps are met. Returns True if one ran."""
        for module in self._modules:
            current = self._get_module_version(module.name)
            # Only consider the lowest pending version (must migrate in order)
            candidates = sorted(
                [s for s in module.migrations if s.version > current],
                key=lambda s: s.version,
            )
            if not candidates:
                continue
            next_step = candidates[0]
            if self._deps_satisfied(next_step.requires):
                with self._conn:
                    next_step.apply(self._conn)
                    self._set_module_version(module.name, next_step.version)
                logger.info(
                    "Migrated module '%s' → v%d", module.name, next_step.version
                )
                return True
        return False

    def _deps_satisfied(self, requires: list[tuple[str, int]]) -> bool:
        return all(
            self._get_module_version(dep_module) >= min_version
            for dep_module, min_version in requires
        )

    def _pending_steps(self) -> list[tuple[str, int]]:
        return [
            (m.name, s.version)
            for m in self._modules
            for s in m.migrations
            if s.version > self._get_module_version(m.name)
        ]

    # ------------------------------------------------------------------
    # Info table
    # ------------------------------------------------------------------

    def _ensure_info_table(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS info (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def _get_module_version(self, name: str) -> int:
        row = self._conn.execute(
            "SELECT value FROM info WHERE key = ?", (f"version:{name}",)
        ).fetchone()
        return int(row["value"]) if row else 0

    def _set_module_version(self, name: str, version: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO info (key, value) VALUES (?, ?)",
            (f"version:{name}", str(version)),
        )
