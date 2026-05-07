import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .core import DatabaseModule, MigrationStep


@dataclass
class SessionRecord:
    token: str
    username: str
    created_at: datetime


class SessionsModule(DatabaseModule):
    name = "sessions"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(version=1, apply=self._migrate_v1),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, username: str) -> str:
        token = secrets.token_hex(32)
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
                (token, username, datetime.now(timezone.utc).isoformat()),
            )
        return token

    def get(self, token: str) -> SessionRecord | None:
        row = self._conn.execute(
            "SELECT token, username, created_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            token=row["token"],
            username=row["username"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def delete(self, token: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
