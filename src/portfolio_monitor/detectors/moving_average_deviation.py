from typing import Annotated

import numpy as np

from portfolio_monitor.data import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class SMADeviationDetector(TimeRangeDetectorBase[float]):
    """Alerts when the current price deviates from the Simple Moving Average by more than a
    fractional threshold. Triggers on both sides (above and below the SMA), making it useful
    for detecting sustained mean-reversion setups or breakouts away from a recent price anchor."""
    display_name = "SMA Deviation"

    @classmethod
    def name(cls) -> str:
        return "SMA_deviation"

    def __init__(
        self,
        threshold: Annotated[float, "Minimum fractional deviation from the SMA to trigger (e.g. 0.05 = 5%)"] = 0.05,
        period: Annotated[str, "Rolling window used to compute the SMA (e.g. '2h', '1d')"] = "2h",
    ) -> None:
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.close

    def _compute_alert_state(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        close_history = np.array(self.values(symbol))
        current_price = aggregate.close
        mean = np.mean(close_history)

        signed_deviation = (current_price - mean) / mean
        deviation = abs(signed_deviation)

        if deviation >= self.threshold:
            direction = "above" if signed_deviation > 0 else "below"
            msg = f"{symbol}: Price {direction} {self.period} simple moving average by {deviation * 100:.2f}%"
            extra = {
                "deviation_percent": float(deviation * 100),
                "simple_moving_average": float(mean),
                "period": self.period,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)
