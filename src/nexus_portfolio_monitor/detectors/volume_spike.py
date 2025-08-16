import numpy as np

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, TimeRangeDetectorBase, DetectorRegistry

@DetectorRegistry.register
class VolumeSpikeDetector(TimeRangeDetectorBase[float]):
    """
    Detector for unusual spikes in trading volume based on multiples of average volume.
    
    This detector tracks trading volume over a specified time period and alerts when
    the current volume exceeds a multiple of the average volume in that period.
    """
    
    @property
    def name(self) -> str:
        return "volume_spike"
    
    def __init__(self, period: str = "2h", threshold: float = 2.0):
        """
        Initialize the volume spike detector with specified parameters.
        
        Args:
            period: Time period to use for calculating average volume (e.g. "2h", "1d").
                    Used for calculating the baseline average volume.
            threshold: Multiple of average volume that triggers an alert (e.g. 2.0 means
                    volume must be at least twice the average to trigger an alert).
        """
        super().__init__(period)
        self.threshold = threshold
    
    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.volume
    
    def _check_alert(self, aggregate: Aggregate) -> Alert | None:
        data = np.array([record.value for record in self.histories[aggregate.symbol]])
        mean = np.mean(data)
        
        if aggregate.volume >= (mean * self.threshold):
            pct_increase = ((aggregate.volume / mean) - 1) * 100
            msg = f"{aggregate.symbol}: Volume spike of {pct_increase:.2f}% over {self.period} average"
            extra = {
                "current_volume": aggregate.volume,
                "average_volume": mean,
                "percent_increase": pct_increase,
            }
            return Alert(aggregate.symbol, self.name, msg, extra, aggregate.date, aggregate)
        return None
