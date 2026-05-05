from datetime import timedelta
from enum import Enum

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.data import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, DetectorBase
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

class AlertDirections(str, Enum):
    ABOVE = "above"
    BELOW = "below"

@DetectorRegistry.register
class PriceValueDetector(DetectorBase):

    @classmethod
    def name(cls) -> str:
        return "price_value"
    
    def __init__(self, limit: float, direction: AlertDirections = AlertDirections.ABOVE) -> None:
        super().__init__()
        self.limit = limit
        self.direction = direction
    
    def update(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        triggered = (
            (self.direction == "above" and aggregate.close > self.limit) 
            or (self.direction == "below" and aggregate.close < self.limit)
        )

        if symbol.asset_type == AssetTypes.Stock:
            price_value = Currency(aggregate.close)
            limit_value = Currency(self.limit)
        else:
            price_value = Currency.usd_price(aggregate.close, symbol.ticker)
            limit_value = Currency.usd_price(self.limit, symbol.ticker)
        
        if triggered:
            msg = f"{aggregate.symbol}: Price {price_value} {self.direction} {limit_value}"
            self._fire_or_update_alert(aggregate.symbol, msg, {
                "limit": self.limit,
                "direction": self.direction
            }, aggregate)
        else:
            self._clear_alert(aggregate.symbol)

    def is_primed(self, symbol: AssetSymbol) -> bool:
        return True

    def prime_age(self) -> timedelta | int:
        return 0
