from dataclasses import dataclass
from datetime import datetime
from nexus_portfolio_monitor.core.currency import Currency

@dataclass
class AssetUpdateRecord:
    ticker: str
    price: Currency | None = None
    time_updated: datetime | None = None
