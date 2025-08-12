from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from nexus_portfolio_monitor.core.currency import Currency


class AssetTypes(Enum):
    Stock = "stock"
    Currency = "currency"
    Crypto = "crypto"
    
class AssetSymbol:
    def __init__(self, ticker: str, asset_type: AssetTypes):
        self.ticker = ticker
        self.asset_type = asset_type
    
    @property
    def symbol(self) -> str:
        return self.ticker

    @property
    def lookup_symbol(self) -> str:
        if self.asset_type == AssetTypes.Stock:
            return self.ticker
        elif self.asset_type == AssetTypes.Currency:
            return f"C:{self.ticker}USD"
        elif self.asset_type == AssetTypes.Crypto:
            return f"X:{self.ticker}USD"
        else:
            raise ValueError(f"Unknown asset type: {self.asset_type}")
    
    def __str__(self) -> str:
        return self.symbol

    def __repr__(self) -> str:
        return f"AssetSymbol(ticker='{self.ticker}', asset_type='{self.asset_type}')"

@dataclass
class AssetUpdateRecord:
    symbol: AssetSymbol
    price: Currency | None = None
    time_updated: datetime | None = None