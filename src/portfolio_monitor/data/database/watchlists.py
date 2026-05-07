import json
import sqlite3
from typing import Any

from portfolio_monitor.core.permissions import PermissionMap, UserPermission
from portfolio_monitor.watchlist.models import Watchlist, WatchlistEntry
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

from .core import DatabaseModule, MigrationStep


class WatchlistsModule(DatabaseModule):
    name = "watchlists"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(version=1, apply=self._migrate_v1),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id    TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS watchlist_permissions (
                watchlist_id TEXT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
                username     TEXT NOT NULL,
                permission   TEXT NOT NULL,
                PRIMARY KEY (watchlist_id, username, permission)
            );

            CREATE TABLE IF NOT EXISTS watchlist_entries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id  TEXT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
                ticker        TEXT NOT NULL,
                asset_type    TEXT NOT NULL DEFAULT 'stock',
                notes         TEXT NOT NULL DEFAULT '',
                target_buy    REAL,
                target_sell   REAL,
                time_added    TEXT,
                initial_price REAL,
                meta          TEXT NOT NULL DEFAULT '{}',
                UNIQUE (watchlist_id, ticker, asset_type)
            );
        """)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_all(self, owner: str | None = None) -> list[Watchlist]:
        if owner is not None:
            rows = self._conn.execute(
                "SELECT id FROM watchlists WHERE owner = ?", (owner,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT id FROM watchlists").fetchall()
        return [wl for r in rows if (wl := self.get(r["id"])) is not None]

    def get(self, watchlist_id: str) -> Watchlist | None:
        row = self._conn.execute(
            "SELECT id, name, owner FROM watchlists WHERE id = ?", (watchlist_id,)
        ).fetchone()
        if row is None:
            return None

        permissions = self._load_permissions(watchlist_id)
        wl = Watchlist(
            name=row["name"],
            id=row["id"],
            owner=row["owner"],
            permissions=permissions,
        )

        entry_rows = self._conn.execute(
            "SELECT ticker, asset_type, notes, target_buy, target_sell,"
            "       time_added, initial_price, meta"
            " FROM watchlist_entries WHERE watchlist_id = ?",
            (watchlist_id,),
        ).fetchall()
        for er in entry_rows:
            wl.entries.append(self._row_to_entry(er))

        return wl

    def upsert(self, watchlist: Watchlist) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO watchlists (id, name, owner) VALUES (?, ?, ?)",
                (watchlist.id, watchlist.name, watchlist.owner),
            )
            self._conn.execute(
                "DELETE FROM watchlist_permissions WHERE watchlist_id = ?", (watchlist.id,)
            )
            if watchlist.permissions:
                for username, perm in watchlist.permissions._entries.items():
                    if perm.read:
                        self._conn.execute(
                            "INSERT INTO watchlist_permissions (watchlist_id, username, permission)"
                            " VALUES (?, ?, 'read')",
                            (watchlist.id, username),
                        )
                    if perm.write:
                        self._conn.execute(
                            "INSERT INTO watchlist_permissions (watchlist_id, username, permission)"
                            " VALUES (?, ?, 'write')",
                            (watchlist.id, username),
                        )
            self._conn.execute(
                "DELETE FROM watchlist_entries WHERE watchlist_id = ?", (watchlist.id,)
            )
            for entry in watchlist.entries:
                self._insert_entry(watchlist.id, entry)

    def delete(self, watchlist_id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM watchlists WHERE id = ?", (watchlist_id,)
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_permissions(self, watchlist_id: str) -> PermissionMap | None:
        rows = self._conn.execute(
            "SELECT username, permission FROM watchlist_permissions WHERE watchlist_id = ?",
            (watchlist_id,),
        ).fetchall()
        if not rows:
            return None
        entries: dict[str, dict[str, bool]] = {}
        for r in rows:
            entries.setdefault(r["username"], {"read": False, "write": False})[r["permission"]] = True
        return PermissionMap({
            u: UserPermission(read=v["read"], write=v["write"])
            for u, v in entries.items()
        })

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> WatchlistEntry:
        return WatchlistEntry.from_dict({
            "ticker": row["ticker"],
            "asset_type": row["asset_type"],
            "notes": row["notes"],
            "target_buy": row["target_buy"],
            "target_sell": row["target_sell"],
            "time_added": row["time_added"],
            "initial_price": row["initial_price"],
            "meta": json.loads(row["meta"]),
        })

    def _insert_entry(self, watchlist_id: str, entry: WatchlistEntry) -> None:
        self._conn.execute(
            "INSERT INTO watchlist_entries"
            " (watchlist_id, ticker, asset_type, notes, target_buy, target_sell,"
            "  time_added, initial_price, meta)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                watchlist_id,
                entry.symbol.ticker,
                entry.symbol.asset_type.value,
                entry.notes,
                entry.target_buy,
                entry.target_sell,
                entry.time_added.isoformat() if entry.time_added else None,
                entry.initial_price,
                json.dumps(entry.meta),
            ),
        )
