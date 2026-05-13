import sqlite3
from typing import Any

from portfolio_monitor.core.currency import CurrencyType
from portfolio_monitor.core.permissions import PermissionMap, UserPermission
from portfolio_monitor.portfolio.models import Asset, Lot, Portfolio
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

from .core import DatabaseModule, MigrationStep


def _split_currency(c: Any) -> tuple[float, str]:
    """Return (amount_float, currency_code) from a Currency instance."""
    val = float(c._value)
    code = c.currency_type.name if c.currency_type != CurrencyType.USD else "USD"
    return val, code


def _currency_str(val: float, code: str) -> str:
    """Reconstruct the string that Currency.parse_number() can read."""
    return str(val) if code == "USD" else f"{val} {code}"


class PortfoliosModule(DatabaseModule):
    name = "portfolios"

    @property
    def migrations(self) -> list[MigrationStep]:
        return [
            MigrationStep(version=1, apply=self._migrate_v1),
        ]

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id    TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS portfolio_permissions (
                portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                username     TEXT NOT NULL,
                permission   TEXT NOT NULL,
                PRIMARY KEY (portfolio_id, username, permission)
            );

            CREATE TABLE IF NOT EXISTS assets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                ticker       TEXT NOT NULL,
                asset_type   TEXT NOT NULL,
                UNIQUE (portfolio_id, ticker, asset_type)
            );

            CREATE TABLE IF NOT EXISTS lots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                quantity    TEXT NOT NULL,
                price       REAL NOT NULL,
                price_cur   TEXT NOT NULL DEFAULT 'USD',
                date        TEXT,
                fees        REAL,
                fees_cur    TEXT,
                rebates     REAL,
                rebates_cur TEXT
            );
        """)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_all(self, owner: str | None = None) -> list[Portfolio]:
        if owner is not None:
            rows = self._conn.execute(
                "SELECT id FROM portfolios WHERE owner = ?", (owner,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT id FROM portfolios").fetchall()
        return [p for r in rows if (p := self.get(r["id"])) is not None]

    def get(self, portfolio_id: str) -> Portfolio | None:
        row = self._conn.execute(
            "SELECT id, name, owner FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        if row is None:
            return None

        permissions = self._load_permissions(portfolio_id)
        portfolio = Portfolio(
            name=row["name"],
            id=row["id"],
            owner=row["owner"],
            permissions=permissions,
        )

        asset_rows = self._conn.execute(
            "SELECT id, ticker, asset_type FROM assets WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchall()
        for ar in asset_rows:
            lots = self._load_lots(ar["id"])
            asset = Asset(
                symbol=AssetSymbol(ar["ticker"], AssetTypes(ar["asset_type"])),
                lots=lots,
                asset_type=ar["asset_type"],
            )
            self._append_asset(portfolio, asset, ar["asset_type"])

        return portfolio

    def upsert(self, portfolio: Portfolio) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO portfolios (id, name, owner) VALUES (?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name = excluded.name, owner = excluded.owner",
                (portfolio.id, portfolio.name, portfolio.owner),
            )
            self._conn.execute(
                "DELETE FROM portfolio_permissions WHERE portfolio_id = ?", (portfolio.id,)
            )
            if portfolio.permissions:
                for username, perm in portfolio.permissions._entries.items():
                    if perm.read:
                        self._conn.execute(
                            "INSERT INTO portfolio_permissions (portfolio_id, username, permission)"
                            " VALUES (?, ?, 'read')",
                            (portfolio.id, username),
                        )
                    if perm.write:
                        self._conn.execute(
                            "INSERT INTO portfolio_permissions (portfolio_id, username, permission)"
                            " VALUES (?, ?, 'write')",
                            (portfolio.id, username),
                        )
            # Cascades to lots via ON DELETE CASCADE
            self._conn.execute(
                "DELETE FROM assets WHERE portfolio_id = ?", (portfolio.id,)
            )
            for asset_type, attr in (
                ("stock", "stocks"),
                ("currency", "currencies"),
                ("crypto", "crypto"),
            ):
                for asset in getattr(portfolio, attr):
                    cursor = self._conn.execute(
                        "INSERT INTO assets (portfolio_id, ticker, asset_type) VALUES (?, ?, ?)",
                        (portfolio.id, asset.symbol.ticker, asset_type),
                    )
                    asset_id = cursor.lastrowid
                    for lot in asset.lots:
                        self._insert_lot(asset_id, lot)

    def delete(self, portfolio_id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM portfolios WHERE id = ?", (portfolio_id,)
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_permissions(self, portfolio_id: str) -> PermissionMap | None:
        rows = self._conn.execute(
            "SELECT username, permission FROM portfolio_permissions WHERE portfolio_id = ?",
            (portfolio_id,),
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

    def _load_lots(self, asset_id: int) -> list[Lot]:
        rows = self._conn.execute(
            "SELECT quantity, price, price_cur, date, fees, fees_cur, rebates, rebates_cur"
            " FROM lots WHERE asset_id = ?",
            (asset_id,),
        ).fetchall()
        return [self._row_to_lot(r) for r in rows]

    @staticmethod
    def _row_to_lot(row: sqlite3.Row) -> Lot:
        d: dict[str, Any] = {
            "quantity": row["quantity"],
            "price": _currency_str(row["price"], row["price_cur"]),
        }
        if row["date"]:
            d["date"] = row["date"]
        if row["fees"] is not None:
            d["fees"] = _currency_str(row["fees"], row["fees_cur"] or "USD")
        if row["rebates"] is not None:
            d["rebates"] = _currency_str(row["rebates"], row["rebates_cur"] or "USD")
        return Lot.from_dict(d)

    def _insert_lot(self, asset_id: int, lot: Lot) -> None:
        price_val, price_cur = _split_currency(lot.price)
        fees_val = fees_cur = rebates_val = rebates_cur = None
        if lot.fees is not None:
            fees_val, fees_cur = _split_currency(lot.fees)
        if lot.rebates is not None:
            rebates_val, rebates_cur = _split_currency(lot.rebates)
        date_str = lot.date.strftime("%Y/%m/%d") if lot.date else None
        self._conn.execute(
            "INSERT INTO lots"
            " (asset_id, quantity, price, price_cur, date, fees, fees_cur, rebates, rebates_cur)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                str(lot.quantity),
                price_val,
                price_cur,
                date_str,
                fees_val,
                fees_cur,
                rebates_val,
                rebates_cur,
            ),
        )

    @staticmethod
    def _append_asset(portfolio: Portfolio, asset: Asset, asset_type: str) -> None:
        if asset_type == "stock":
            portfolio.stocks.append(asset)
        elif asset_type == "currency":
            portfolio.currencies.append(asset)
        elif asset_type == "crypto":
            portfolio.crypto.append(asset)
