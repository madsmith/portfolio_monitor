from typing import Annotated

import numpy as np

from portfolio_monitor.data import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class ZScoreVolumeDetector(TimeRangeDetectorBase[float]):
    """Alerts when volume deviates from the rolling mean by more than N standard deviations.
    More statistically precise than a raw multiple — adapts to the actual spread of volume
    over the window, making it less prone to false positives during naturally high-volume periods."""
    display_name = "Z-Score Volume"

    @classmethod
    def name(cls) -> str:
        return "zscore_volume"

    def __init__(
        self,
        threshold: Annotated[float, "Minimum Z-score (standard deviations above mean) required to trigger"] = 1.0,
        period: Annotated[str, "Rolling window for computing mean and standard deviation of volume (e.g. '2h', '1h')"] = "2h",
    ) -> None:
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
