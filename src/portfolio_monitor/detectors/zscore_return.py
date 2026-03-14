import numpy as np

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class ZScoreReturnDetector(TimeRangeDetectorBase[float]):
    """
    Detector for returns that deviate significantly from historical distribution.
    """

    @classmethod
    def name(cls) -> str:
        return "zscore_return"

    def __init__(self, period: str = "2h", threshold: float = 2.0) -> None:
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.close

    def _compute_alert_state(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        close_history = self.values(symbol)

        if len(close_history) < 3:
            self._clear_alert(symbol)
            return

        return_values = self._calculate_returns(close_history)

        if len(return_values) < 2:
            self._clear_alert(symbol)
            return

        previous_close = close_history[-2]
        current_return = (aggregate.close - previous_close) / previous_close
        mean_return = np.mean(return_values)
        std_dev = np.std(return_values, ddof=1)

        if std_dev == 0:
            self._clear_alert(symbol)
            return

        z_score = (current_return - mean_return) / std_dev

        if np.abs(z_score) >= self.threshold:
            direction = "above" if z_score > 0 else "below"
            current_return_percent = current_return * 100
            msg = (
                f"{symbol}: Return of {current_return_percent:.2f}% is {direction} "
                f"{self.threshold}x standard deviations from {self.period} average return."
            )
            extra = {
                "z_score": float(z_score),
                "current_return_percent": float(current_return_percent),
                "average_return_percent": float(mean_return * 100),
                "standard_deviation": float(std_dev),
                "period": self.period,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)

    def _calculate_returns(self, close_history: list[float]) -> list[float]:
        if len(close_history) <= 1:
            return []
        return [
            (close_history[i] - close_history[i - 1]) / close_history[i - 1]
            for i in range(1, len(close_history))
        ]
