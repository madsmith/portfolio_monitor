import numpy as np

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class SMADeviationDetector(TimeRangeDetectorBase[float]):
    """
    Detector for price deviations from a Simple Moving Average (SMA).
    """

    @classmethod
    def name(cls) -> str:
        return "SMA_deviation"

    def __init__(self, period: str = "2h", threshold: float = 0.05) -> None:
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
