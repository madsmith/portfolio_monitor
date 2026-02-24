import numpy as np

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import Alert, DetectorRegistry, TimeRangeDetectorBase


@DetectorRegistry.register
class SMADeviationDetector(TimeRangeDetectorBase[float]):
    """
    Detector for price deviations from a Simple Moving Average (SMA).

    This detector tracks asset prices over a specified time period and calculates
    a simple moving average of the closing prices. It generates alerts when the
    current price deviates from this average by more than the specified threshold
    percentage, which can indicate significant trend changes or unusual price action.
    """

    @property
    def name(self) -> str:
        return "SMA_deviation"

    def __init__(self, period: str = "2h", threshold: float = 0.05):
        """
        Initialize the Simple Moving Average (SMA) deviation detector with specified parameters.

        Args:
            period: Time period for the moving average calculation (e.g., "2h", "1d").
                    Used for establishing the baseline price average.
            threshold: Percentage deviation from the moving average that triggers an alert
                    (e.g., 0.05 means 5% deviation will trigger an alert). This is
                    expressed as a decimal, not a percentage.
        """
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.close

    def _check_alert(self, aggregate: Aggregate) -> Alert | None:
        close_history = np.array(self.values(aggregate.symbol))

        current_price = aggregate.close
        mean = np.mean(close_history)

        deviation = abs(current_price - mean) / mean

        if abs(deviation) >= self.threshold:
            direction = "above" if deviation > 0 else "below"
            msg = f"{aggregate.symbol}: Price {direction} {self.period} simple moving average by {abs(deviation) * 100:.2f}%"
            extra = {
                "deviation_percent": float(deviation * 100),
                "simple_moving_average": float(mean),
                "period": self.period,
            }
            return self.alert(aggregate, msg, extra)
        return None
