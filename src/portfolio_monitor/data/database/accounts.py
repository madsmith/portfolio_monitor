import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from .core import DatabaseModule, MigrationStep


class AccountRole(StrEnum):
    admin = "admin"
    normal = "normal"


@dataclass
class AccountRecord:
    username: str
    password_hash: str
    role: AccountRole


class AccountsModule(DatabaseModule):
    name = "accounts"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(version=1, apply=self._migrate_v1),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL
            )
        """)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_all(self) -> list[AccountRecord]:
        rows = self._conn.execute(
            "SELECT username, password_hash, role FROM accounts"
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, username: str) -> AccountRecord | None:
        row = self._conn.execute(
            "SELECT username, password_hash, role FROM accounts WHERE username = ?",
            (username,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def create(self, username: str, password_hash: str, role: AccountRole) -> AccountRecord:
        with self._conn:
            self._conn.execute(
                "INSERT INTO accounts (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, str(role)),
            )
        return AccountRecord(username=username, password_hash=password_hash, role=role)

    def delete(self, username: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM accounts WHERE username = ?", (username,)
            )
        return cursor.rowcount > 0

    def update_role(self, username: str, role: AccountRole) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE accounts SET role = ? WHERE username = ?", (str(role), username)
            )
        return cursor.rowcount > 0

    def update_password(self, username: str, password_hash: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE accounts SET password_hash = ? WHERE username = ?",
                (password_hash, username),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AccountRecord:
        return AccountRecord(
            username=row["username"],
            password_hash=row["password_hash"],
            role=AccountRole(row["role"]),
        )
