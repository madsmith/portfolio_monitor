import json
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any

from .core import DatabaseModule, MigrationStep


@dataclass
class AlertRule:
    id: str
    owner: str
    ticker: str | None
    asset_type: str | None
    kind: str
    args: dict[str, Any]


@dataclass
class AlertChannelConfig:
    id: str
    type: str
    name: str
    config: dict[str, Any]


@dataclass
class AlertChannelSub:
    id: str
    owner: str
    channel_config_id: str
    target: str
    mode: str  # "off" | "default" | "opt_in"


@dataclass
class AlertRecord:
    id: str
    owner: str
    ticker: str
    asset_type: str
    kind: str
    message: str
    extra: dict[str, Any]
    at: str
    updated_at: str
    read: bool
    deleted: bool


class AlertsModule(DatabaseModule):
    name = "alerts"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(version=1, apply=self._migrate_v1),
            MigrationStep(version=2, apply=self._migrate_v2),
            MigrationStep(version=3, apply=self._migrate_v3),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id         TEXT PRIMARY KEY,
                owner      TEXT NOT NULL,
                ticker     TEXT,
                asset_type TEXT,
                kind       TEXT NOT NULL,
                args       TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS alert_channels (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                owner   TEXT NOT NULL,
                type    TEXT NOT NULL,
                config  TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1
            );
        """)

    def _migrate_v3(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            DROP TABLE IF EXISTS alert_channels;

            CREATE TABLE IF NOT EXISTS alert_channel_configs (
                id     TEXT PRIMARY KEY,
                type   TEXT NOT NULL,
                name   TEXT NOT NULL,
                config TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS alert_channels (
                id                TEXT PRIMARY KEY,
                owner             TEXT NOT NULL,
                channel_config_id TEXT NOT NULL,
                target            TEXT NOT NULL DEFAULT '',
                mode              TEXT NOT NULL DEFAULT 'default'
            );
            CREATE INDEX IF NOT EXISTS idx_alert_channels_owner
                ON alert_channels(owner);

            CREATE TABLE IF NOT EXISTS alert_rule_channel_overrides (
                rule_id         TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                PRIMARY KEY (rule_id, subscription_id)
            );
        """)

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_records (
                id         TEXT PRIMARY KEY,
                owner      TEXT NOT NULL,
                ticker     TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                kind       TEXT NOT NULL,
                message    TEXT NOT NULL,
                extra      TEXT NOT NULL DEFAULT '{}',
                at         TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                read       INTEGER NOT NULL DEFAULT 0,
                deleted    INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_alert_records_owner
                ON alert_records(owner);
        """)

    # ------------------------------------------------------------------
    # alert_rules
    # ------------------------------------------------------------------

    def get_all_rules(self) -> list[AlertRule]:
        rows = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, args FROM alert_rules"
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_rules(self, owner: str) -> list[AlertRule]:
        rows = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, args FROM alert_rules WHERE owner = ?",
            (owner,),
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_rule(self, id: str) -> AlertRule | None:
        row = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, args FROM alert_rules WHERE id = ?",
            (id,),
        ).fetchone()
        return self._row_to_rule(row) if row else None

    def add_rule(
        self,
        owner: str,
        ticker: str | None,
        asset_type: str | None,
        kind: str,
        args: dict[str, Any],
        id: str | None = None,
    ) -> AlertRule:
        rule_id = id or secrets.token_hex(16)
        with self._conn:
            self._conn.execute(
                "INSERT INTO alert_rules (id, owner, ticker, asset_type, kind, args)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (rule_id, owner, ticker, asset_type, kind, json.dumps(args)),
            )
        return AlertRule(
            id=rule_id,
            owner=owner,
            ticker=ticker,
            asset_type=asset_type,
            kind=kind,
            args=args,
        )

    def update_rule(self, id: str, args: dict[str, Any]) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE alert_rules SET args = ? WHERE id = ?",
                (json.dumps(args), id),
            )
        return cursor.rowcount > 0

    def delete_rule(self, id: str, owner: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM alert_rules WHERE id = ? AND owner = ?",
                (id, owner),
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # alert_channel_configs  (admin-managed, no owner filter)
    # ------------------------------------------------------------------

    def get_all_channel_configs(self) -> list[AlertChannelConfig]:
        rows = self._conn.execute(
            "SELECT id, type, name, config FROM alert_channel_configs"
        ).fetchall()
        return [self._row_to_channel_config(r) for r in rows]

    def get_channel_config(self, id: str) -> AlertChannelConfig | None:
        row = self._conn.execute(
            "SELECT id, type, name, config FROM alert_channel_configs WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_channel_config(row) if row else None

    def add_channel_config(self, type: str, name: str, config: dict[str, Any]) -> AlertChannelConfig:
        cfg_id = secrets.token_hex(16)
        with self._conn:
            self._conn.execute(
                "INSERT INTO alert_channel_configs (id, type, name, config) VALUES (?, ?, ?, ?)",
                (cfg_id, type, name, json.dumps(config)),
            )
        return AlertChannelConfig(id=cfg_id, type=type, name=name, config=config)

    def update_channel_config(self, id: str, name: str, config: dict[str, Any]) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE alert_channel_configs SET name = ?, config = ? WHERE id = ?",
                (name, json.dumps(config), id),
            )
        return cursor.rowcount > 0

    def delete_channel_config(self, id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM alert_channel_configs WHERE id = ?", (id,)
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # alert_channels  (user subscriptions)
    # ------------------------------------------------------------------

    def get_subscriptions(self, owner: str) -> list[AlertChannelSub]:
        rows = self._conn.execute(
            "SELECT id, owner, channel_config_id, target, mode FROM alert_channels WHERE owner = ?",
            (owner,),
        ).fetchall()
        return [self._row_to_sub(r) for r in rows]

    def get_subscription(self, id: str) -> AlertChannelSub | None:
        row = self._conn.execute(
            "SELECT id, owner, channel_config_id, target, mode FROM alert_channels WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_sub(row) if row else None

    def add_subscription(
        self,
        owner: str,
        channel_config_id: str,
        target: str,
        mode: str = "default",
    ) -> AlertChannelSub:
        sub_id = secrets.token_hex(16)
        with self._conn:
            self._conn.execute(
                "INSERT INTO alert_channels (id, owner, channel_config_id, target, mode)"
                " VALUES (?, ?, ?, ?, ?)",
                (sub_id, owner, channel_config_id, target, mode),
            )
        return AlertChannelSub(
            id=sub_id, owner=owner, channel_config_id=channel_config_id,
            target=target, mode=mode,
        )

    def update_subscription(self, id: str, target: str, mode: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE alert_channels SET target = ?, mode = ? WHERE id = ?",
                (target, mode, id),
            )
        return cursor.rowcount > 0

    def delete_subscription(self, id: str, owner: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM alert_channels WHERE id = ? AND owner = ?", (id, owner)
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # alert_rule_channel_overrides  (per-rule opt-in)
    # ------------------------------------------------------------------

    def add_rule_channel_override(self, rule_id: str, subscription_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO alert_rule_channel_overrides (rule_id, subscription_id)"
                " VALUES (?, ?)",
                (rule_id, subscription_id),
            )

    def remove_rule_channel_override(self, rule_id: str, subscription_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM alert_rule_channel_overrides WHERE rule_id = ? AND subscription_id = ?",
                (rule_id, subscription_id),
            )

    def has_rule_channel_override(self, rule_id: str, subscription_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM alert_rule_channel_overrides WHERE rule_id = ? AND subscription_id = ?",
            (rule_id, subscription_id),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # alert_records
    # ------------------------------------------------------------------

    def push_record(self, owner: str, alert_dict: dict[str, Any]) -> tuple["AlertRecord", bool]:
        """Insert or update an alert record. Returns (record, is_new).

        If the record exists but is soft-deleted, the update is skipped so
        that a deleted alert cannot resurface via a detector re-fire.
        """
        alert_id = alert_dict["id"]
        ticker_info = alert_dict["ticker"]
        ticker = ticker_info["ticker"] if isinstance(ticker_info, dict) else str(ticker_info)
        asset_type = ticker_info.get("asset_type", "") if isinstance(ticker_info, dict) else ""
        existing_row = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, message, extra, at, updated_at, read, deleted"
            " FROM alert_records WHERE id = ?", (alert_id,)
        ).fetchone()
        if existing_row is not None:
            existing = self._row_to_record(existing_row)
            if existing.deleted:
                return existing, False
            with self._conn:
                self._conn.execute(
                    "UPDATE alert_records SET message = ?, extra = ?, updated_at = ? WHERE id = ?",
                    (alert_dict["message"],
                     json.dumps(alert_dict.get("extra") or {}),
                     alert_dict["updated_at"], alert_id),
                )
            row = self._conn.execute(
                "SELECT id, owner, ticker, asset_type, kind, message, extra, at, updated_at, read, deleted"
                " FROM alert_records WHERE id = ?", (alert_id,)
            ).fetchone()
            return self._row_to_record(row), False
        with self._conn:
            self._conn.execute(
                "INSERT INTO alert_records"
                " (id, owner, ticker, asset_type, kind, message, extra, at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (alert_id, owner, ticker, asset_type,
                 alert_dict["kind"], alert_dict["message"],
                 json.dumps(alert_dict.get("extra") or {}),
                 alert_dict["at"], alert_dict["updated_at"]),
            )
        row = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, message, extra, at, updated_at, read, deleted"
            " FROM alert_records WHERE id = ?", (alert_id,)
        ).fetchone()
        return self._row_to_record(row), True

    def get_records(self, owner: str, limit: int = 50) -> list["AlertRecord"]:
        rows = self._conn.execute(
            "SELECT id, owner, ticker, asset_type, kind, message, extra, at, updated_at, read, deleted"
            " FROM alert_records WHERE owner = ? AND deleted = 0 ORDER BY at DESC LIMIT ?",
            (owner, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_unread_count(self, owner: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM alert_records WHERE owner = ? AND read = 0 AND deleted = 0",
            (owner,),
        ).fetchone()
        return row[0]

    def mark_record_read(self, owner: str, alert_id: str) -> int:
        with self._conn:
            self._conn.execute(
                "UPDATE alert_records SET read = 1 WHERE id = ? AND owner = ?",
                (alert_id, owner),
            )
        return self.get_unread_count(owner)

    def mark_all_records_read(self, owner: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE alert_records SET read = 1 WHERE owner = ? AND deleted = 0",
                (owner,),
            )

    def delete_record(self, owner: str, alert_id: str) -> int:
        with self._conn:
            self._conn.execute(
                "UPDATE alert_records SET deleted = 1 WHERE id = ? AND owner = ?",
                (alert_id, owner),
            )
        return self.get_unread_count(owner)

    def clear_records(self, owner: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE alert_records SET deleted = 1 WHERE owner = ?",
                (owner,),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> "AlertRecord":
        return AlertRecord(
            id=row["id"],
            owner=row["owner"],
            ticker=row["ticker"],
            asset_type=row["asset_type"],
            kind=row["kind"],
            message=row["message"],
            extra=json.loads(row["extra"]),
            at=row["at"],
            updated_at=row["updated_at"],
            read=bool(row["read"]),
            deleted=bool(row["deleted"]),
        )

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> AlertRule:
        return AlertRule(
            id=row["id"],
            owner=row["owner"],
            ticker=row["ticker"],
            asset_type=row["asset_type"],
            kind=row["kind"],
            args=json.loads(row["args"]),
        )

    @staticmethod
    def _row_to_channel_config(row: sqlite3.Row) -> AlertChannelConfig:
        return AlertChannelConfig(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            config=json.loads(row["config"]),
        )

    @staticmethod
    def _row_to_sub(row: sqlite3.Row) -> AlertChannelSub:
        return AlertChannelSub(
            id=row["id"],
            owner=row["owner"],
            channel_config_id=row["channel_config_id"],
            target=row["target"],
            mode=row["mode"],
        )
