import numpy as np

from portfolio_monitor.detectors import Alert, TimeRangeDetectorBase, DetectorRegistry
from portfolio_monitor.data.aggregate_cache import Aggregate

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
        volume_history = np.array(self.values(aggregate.symbol))
        
        if len(volume_history) < 2:
            return None
        
        mean = np.mean(volume_history)
        std_dev = np.std(volume_history, ddof=1)

        if std_dev == 0:
            return None
        
        z_score = (aggregate.volume - mean) / std_dev

        if z_score > self.threshold:
            direction = "above" if z_score > 0 else "below"
            msg = f"{aggregate.symbol}: Volume spike of {z_score:.2f} {direction} {self.threshold}x standard deviations from {self.period} average volume."
            extra = {
                "z_score": float(z_score),
                "current_volume": aggregate.volume,
                "average_volume": float(mean),
                "standard_deviation": float(std_dev),
                "period": self.period,
            }
            return self.alert(aggregate, msg, extra)
        return None