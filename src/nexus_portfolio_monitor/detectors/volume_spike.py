from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import NamedTuple

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.core.datetime import parse_period
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol

class VolumeRecord(NamedTuple):
    """Record of volume with timestamp"""
    timestamp: datetime
    volume: float

@DetectorRegistry.register
class VolumeSpikeDetector(Detector):
    """Detector for unusual spikes in trading volume"""
    
    @property
    def name(self) -> str:
        return "volume_spike"
    
    def __init__(self, period: str = "2h", threshold: float = 2.0):
        """
        Args:
            period: Time period to use for calculating average volume (default: "2h")
                   Can be specified as "Xd", "Xh", "Xm", "Xs" for days, hours, minutes, seconds
            threshold: Multiple of average volume that triggers an alert
        """
        self.period = period
        self.period_delta = parse_period(period)
        self.threshold_mult = threshold
        self.volume_histories: dict[AssetSymbol, list[VolumeRecord]] = defaultdict(list)
        
    def _clean_old_volumes(self, symbol: AssetSymbol, current_time: datetime) -> None:
        """Remove volume records older than the lookback period"""
        if symbol not in self.volume_histories:
            return
            
        cutoff_time = current_time - self.period_delta
        
        # Filter out old records
        history = self.volume_histories[symbol]
        self.volume_histories[symbol] = [record for record in history if record.timestamp >= cutoff_time]
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        symbol = aggregate.symbol

        # Clean up old volume records
        self._clean_old_volumes(symbol, aggregate.date)
            
        # Add current volume to history
        self.volume_histories[symbol].append(VolumeRecord(aggregate.date, aggregate.volume))
        
        # Need enough history to calculate baseline (at least 5 points)
        if len(self.volume_histories[symbol]) < 5:
            return None
            
        # Calculate average volume (excluding the current volume)
        previous_volumes = [r.volume for r in self.volume_histories[symbol][:-1]]
        if not previous_volumes:
            return None
            
        avg_volume = mean(previous_volumes)
        
        # Check if current volume exceeds threshold
        if aggregate.volume >= (avg_volume * self.threshold_mult):
            pct_increase = ((aggregate.volume / avg_volume) - 1) * 100
            msg = f"{symbol}: Volume spike of {pct_increase:.2f}% over {self.period} average"
            extra = {
                "current_volume": aggregate.volume,
                "average_volume": avg_volume,
                "percent_increase": pct_increase,
            }
            
            return Alert(symbol, self.name, msg, extra, aggregate.date, aggregate)
            
        return None
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        The VolumeSpikeDetector needs data from the configured period to calculate average volume.
        """
        # Ensure we have at least a minimum amount of data (5 samples)
        min_lookback = sample_interval * 5
        
        # Use the maximum of either the configured period or the minimum lookback
        effective_lookback = max(self.period_delta, min_lookback)
        
        # Return the earliest time needed
        return current_time - effective_lookback
