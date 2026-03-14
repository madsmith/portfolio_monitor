import numpy as np

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class ZScoreVolumeDetector(TimeRangeDetectorBase[float]):
    """
    Detector for unusual volume spikes based on standard deviation (Z-score).
    """

    @classmethod
    def name(cls) -> str:
        return "zscore_volume"

    def __init__(self, period: str = "2h", threshold: float = 1.0) -> None:
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.volume

    def _compute_alert_state(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        volume_history = np.array(self.values(symbol))

        if len(volume_history) < 2:
            self._clear_alert(symbol)
            return

        mean = np.mean(volume_history)
        std_dev = np.std(volume_history, ddof=1)

        if std_dev == 0:
            self._clear_alert(symbol)
            return

        z_score = (aggregate.volume - mean) / std_dev

        if z_score > self.threshold:
            direction = "above" if z_score > 0 else "below"
            msg = (
                f"{symbol}: Volume spike of {z_score:.2f} {direction} "
                f"{self.threshold}x standard deviations from {self.period} average volume."
            )
            extra = {
                "z_score": float(z_score),
                "current_volume": aggregate.volume,
                "average_volume": float(mean),
                "standard_deviation": float(std_dev),
                "period": self.period,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)
