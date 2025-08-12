
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate

@dataclass
class Alert:
    ticker: str
    kind: str            # Should match detector's name (e.g., "pct_change", "zscore", "atr", "ma_dev", "vol_spike")
    severity: float      # normalized magnitude (e.g., abs z, multiple of ATR, %)
    message: str
    at: datetime
    aggregate: Aggregate  # The price aggregate that triggered the alert

class Detector(Protocol):
    @property
    def name(self) -> str:
        """Return the detector's name (used for alert kind)"""
        ...
    
    def update(self, ticker: str, aggregate: Aggregate) -> Alert | None:
        """Update the detector with the latest aggregate for the given ticker"""
        ...