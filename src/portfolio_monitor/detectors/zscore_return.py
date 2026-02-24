import numpy as np

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import Alert, DetectorRegistry, TimeRangeDetectorBase


@DetectorRegistry.register
class ZScoreReturnDetector(TimeRangeDetectorBase[float]):
    """
    Detector for returns that deviate significantly from historical distribution.

    This detector tracks asset price movements over a specified time period and alerts
    when the current price movement (return) deviates significantly from the historical
    distribution of returns, measured in standard deviations (Z-score).
    """

    @property
    def name(self) -> str:
        return "zscore_return"

    def __init__(self, period: str = "2h", threshold: float = 2.0):
        """
        Initialize the Z-score return detector with specified parameters.

        Args:
            period: Time period to use for calculating return statistics (e.g. "2h", "1d").
                    Used for establishing the baseline return distribution.
            threshold: Z-score threshold that triggers an alert (e.g. 2.0 means
                return must be at least 2 standard deviations from the mean).
        """
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.close

    def _check_alert(self, aggregate: Aggregate) -> Alert | None:
        close_history = self.values(aggregate.symbol)

        if len(close_history) < 3:
            return None

        return_values = self._calculate_returns(close_history)

        if len(return_values) < 2:
            return None

        previous_close = close_history[-2]
        current_return = (aggregate.close - previous_close) / previous_close
        mean_return = np.mean(return_values)
        std_dev = np.std(return_values, ddof=1)

        if std_dev == 0:
            return None

        z_score = (current_return - mean_return) / std_dev

        if np.abs(z_score) >= self.threshold:
            direction = "above" if z_score > 0 else "below"
            current_return_percent = current_return * 100
            msg = f"{aggregate.symbol}: Return of {current_return_percent:.2f}% is {direction} {self.threshold}x standard deviations from {self.period} average return."
            extra = {
                "z_score": float(z_score),
                "current_return_percent": float(current_return_percent),
                "average_return_percent": float(mean_return * 100),
                "standard_deviation": float(std_dev),
                "period": self.period,
            }
            return self.alert(aggregate, msg, extra)
        return None

    def _calculate_returns(self, close_history: list[float]) -> list[float]:
        """Calculate percentage returns from price history"""
        if len(close_history) <= 1:
            return []

        returns = []

        for i in range(1, len(close_history)):
            return_value = (close_history[i] - close_history[i - 1]) / close_history[
                i - 1
            ]
            returns.append(return_value)

        return returns
