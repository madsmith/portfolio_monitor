from typing import Annotated

import numpy as np

from portfolio_monitor.data import Aggregate
from portfolio_monitor.detectors import DetectorRegistry, TimeRangeDetectorBase
from portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class VolumeSpikeDetector(TimeRangeDetectorBase[float]):
    """Alerts when current bar volume exceeds the rolling mean volume by a set multiple.
    Uses a simple average over the trailing window — good for catching obvious bursts
    of activity without requiring statistical warmup."""

    @classmethod
    def name(cls) -> str:
        return "volume_spike"

    def __init__(
        self,
        period: Annotated[str, "Rolling window over which average volume is calculated (e.g. '2h', '30m')"] = "2h",
        threshold: Annotated[float, "Minimum multiple of average volume to trigger (e.g. 2.0 = current bar ≥ 2× average)"] = 2.0,
    ) -> None:
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.volume

    def _compute_alert_state(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        volume_history = np.array(self.values(symbol))
        mean = np.mean(volume_history)

        if aggregate.volume >= (mean * self.threshold):
            pct_increase = ((aggregate.volume / mean) - 1) * 100
            msg = f"{symbol}: Volume spike of {pct_increase:.2f}% over {self.period} average"
            extra = {
                "current_volume": aggregate.volume,
                "average_volume": float(mean),
                "percent_increase": float(pct_increase),
                "period": self.period,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)
