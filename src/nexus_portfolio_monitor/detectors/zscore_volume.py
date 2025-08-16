import numpy as np

from nexus_portfolio_monitor.detectors.base import Alert, TimeRangeDetectorBase, DetectorRegistry
from nexus_portfolio_monitor.data.aggregate_cache import Aggregate

@DetectorRegistry.register
class ZScoreVolumeDetector(TimeRangeDetectorBase[float]):
    """
    Detector for unusual volume spikes based on standard deviation (Z-score).
    
    This detector tracks trading volume over a specified time period and alerts
    when the current volume exceeds the mean by a certain number of standard 
    deviations, which is a more statistically robust method than simple multiples.
    """
    
    @property
    def name(self) -> str:
        return "zscore_volume"
    
    def __init__(self, period: str = "2h", threshold: float = 1.0):
        """
        Initialize the Z-score volume detector with specified parameters.
        
        Args:
            period: Time period to use for calculating volume statistics (e.g. "2h", "1d").
                    Used for calculating the baseline volume distribution.
            threshold: Z-score threshold that triggers an alert (e.g. 1.0 means
                    volume must be at least 1 standard deviation above the mean).
        """
        super().__init__(period)
        self.threshold = threshold
    
    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.volume
    
    def _check_alert(self, aggregate: Aggregate) -> Alert | None:
        data = np.array([record.value for record in self.histories[aggregate.symbol]])
        mean = np.mean(data)
        std_dev = np.std(data)
        z_score = (aggregate.volume - mean) / std_dev

        if z_score > self.threshold:
            msg = f"{aggregate.symbol}: Volume spike of {z_score:.2f} standard deviations over {self.period} average"
            extra = {
                "z_score": z_score,
                "current_volume": aggregate.volume,
                "average_volume": mean,
                "standard_deviation": std_dev,
            }
            return Alert(aggregate.symbol, self.name, msg, extra, aggregate.date, aggregate)
        return None