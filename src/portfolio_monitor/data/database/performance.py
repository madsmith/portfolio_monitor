import sqlite3
from datetime import datetime

from .core import DatabaseModule, MigrationStep


class PortfolioPerformanceModule(DatabaseModule):
    name = "performance"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(
                version=1,
                apply=self._migrate_v1,
                requires=[("portfolios", 1)],
            ),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolio_performance (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                recorded_at  TEXT NOT NULL,
                total_value  REAL,
                cost_basis   REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pp_portfolio_hour
                ON portfolio_performance(portfolio_id, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_pp_portfolio_time
                ON portfolio_performance(portfolio_id, recorded_at DESC);
        """)

    def insert_snapshot(
        self,
        portfolio_id: str,
        recorded_at: datetime,
        total_value: float | None,
        cost_basis: float,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO portfolio_performance"
                " (portfolio_id, recorded_at, total_value, cost_basis)"
                " VALUES (?, ?, ?, ?)",
                (portfolio_id, recorded_at.isoformat(), total_value, cost_basis),
            )

    def get_range(
        self,
        portfolio_id: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[dict]:
        rows = self._conn.execute(
            "SELECT recorded_at, total_value, cost_basis"
            " FROM portfolio_performance"
            " WHERE portfolio_id = ? AND recorded_at >= ? AND recorded_at <= ?"
            " ORDER BY recorded_at ASC",
            (portfolio_id, from_dt.isoformat(), to_dt.isoformat()),
        ).fetchall()
        return [
            {
                "recorded_at": row["recorded_at"],
                "total_value": row["total_value"],
                "cost_basis": row["cost_basis"],
            }
            for row in rows
        ]
