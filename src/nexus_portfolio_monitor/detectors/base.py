
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate

@dataclass
class Alert:
    ticker: str
    kind: str            # e.g., "pct_change", "zscore", "atr", "ma_dev", "vol_spike"
    severity: float      # normalized magnitude (e.g., abs z, multiple of ATR, %)
    message: str
    at: datetime

class Detector(Protocol):
    def update(self, ticker: str, aggregate: Aggregate) -> Alert | None: ...