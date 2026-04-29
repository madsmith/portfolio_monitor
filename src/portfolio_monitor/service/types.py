import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from portfolio_monitor.core import Currency

logger = logging.getLogger(__name__)


class AssetTypes(Enum):
    Stock = "stock"
    Currency = "currency"
    Crypto = "crypto"


@dataclass(frozen=True)
class AssetSymbol:
    ticker: str
    asset_type: AssetTypes

    def __post_init__(self) -> None:
        if isinstance(self.asset_type, str):
            logger.warning(
                "AssetSymbol received a primitive string for asset_type=%r; "
                "upconverting to AssetTypes. Use AssetTypes directly.",
                self.asset_type,
            )
            object.__setattr__(self, "asset_type", AssetTypes(self.asset_type))

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

    def to_dict(self) -> dict[str, Any]:
        return {"ticker": self.ticker, "type": self.asset_type.value}

    def __repr__(self) -> str:
        return f"AssetSymbol('{self.ticker}', '{self.asset_type.value}')"

    def __str__(self) -> str:
        if self.asset_type == AssetTypes.Stock:
            return f"{self.ticker}"
        return f"{self.ticker} ({self.asset_type.value})"


@dataclass
class AssetUpdateRecord:
    symbol: AssetSymbol
    price: Currency | None = None
    time_updated: datetime | None = None
