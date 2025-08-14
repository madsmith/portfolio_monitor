from collections import deque
from statistics import mean
from datetime import datetime, timedelta

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class VolumeSpikeDetector(Detector):
    """Detector for unusual spikes in trading volume"""
    
    @property
    def name(self) -> str:
        return "volume_spike"
    
    def __init__(self, lookback_period: int = 60, threshold: float = 2.0):
        """
        Args:
            lookback_period: Number of samples to use for calculating average volume (default: 60 samples)
            threshold: Multiple of average volume that triggers an alert
        """
        self.lookback_period = lookback_period
        self.threshold_mult = threshold
        self.volume_histories: dict[AssetSymbol, deque[float]] = {}
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        symbol = aggregate.symbol
        # Initialize history for this ticker if it doesn't exist
        if symbol not in self.volume_histories:
            self.volume_histories[symbol] = deque(maxlen=self.lookback_period)
            
        # Add current volume to history
        self.volume_histories[symbol].append(aggregate.volume)
        
        # Need enough history to calculate baseline
        if len(self.volume_histories[symbol]) < self.lookback_period:
            return None
            
        # Calculate average volume (excluding the current volume)
        previous_volumes = list(self.volume_histories[symbol])[:-1]
        if not previous_volumes:
            return None
            
        avg_volume = mean(previous_volumes)
        
        # Check if current volume exceeds threshold
        if aggregate.volume >= (avg_volume * self.threshold_mult):
            pct_increase = ((aggregate.volume / avg_volume) - 1) * 100
            msg = f"{symbol}: Volume spike of {pct_increase:.2f}% over {self.lookback_period-1} sample average"
            severity = aggregate.volume / avg_volume
            
            return Alert(symbol, self.name, severity, msg, aggregate.date, aggregate)
            
        return None
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        The VolumeSpikeDetector needs lookback_period samples to calculate average volume.
        """
        # Need lookback_period samples for the volume history
        required_samples = self.lookback_period
        
        # Calculate total time needed
        total_time_needed = sample_interval * required_samples
        
        return current_time - total_time_needed
