from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from portfolio_monitor.core import Currency, parse_date
from portfolio_monitor.service.types import AssetSymbol, AssetTypes


@dataclass
class WatchlistEntry:
    """A single symbol being watched, with optional metadata and alert config."""

    symbol: AssetSymbol
    alerts: dict[str, Any] = field(default_factory=dict)   # kind → args
    notes: str = ""
    target_buy: float | None = None
    target_sell: float | None = None
    time_added: datetime | None = None   # set automatically on add
    initial_price: float | None = None  # price at time of addition
    meta: dict[str, Any] = field(default_factory=dict)

    # Runtime only — not persisted to YAML
    current_price: Currency | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatchlistEntry":
        ticker = data["ticker"]
        asset_type = AssetTypes(data.get("asset_type", "stock"))
        symbol = AssetSymbol(ticker, asset_type)

        time_added: datetime | None = None
        raw_time = data.get("time_added")
        if raw_time:
            if isinstance(raw_time, datetime):
                time_added = raw_time
            else:
                time_added = parse_date(str(raw_time))

        return cls(
            symbol=symbol,
            alerts=dict(data.get("alerts") or {}),
            notes=str(data.get("notes") or ""),
            target_buy=float(data["target_buy"]) if data.get("target_buy") is not None else None,
            target_sell=float(data["target_sell"]) if data.get("target_sell") is not None else None,
            time_added=time_added,
            initial_price=float(data["initial_price"]) if data.get("initial_price") is not None else None,
            meta=dict(data.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ticker": self.symbol.ticker,
            "asset_type": self.symbol.asset_type.value,
        }
        if self.notes:
            d["notes"] = self.notes
        if self.target_buy is not None:
            d["target_buy"] = self.target_buy
        if self.target_sell is not None:
            d["target_sell"] = self.target_sell
        if self.time_added is not None:
            d["time_added"] = self.time_added.isoformat()
        if self.initial_price is not None:
            d["initial_price"] = self.initial_price
        if self.meta:
            d["meta"] = self.meta
        if self.alerts:
            d["alerts"] = self.alerts
        return d

