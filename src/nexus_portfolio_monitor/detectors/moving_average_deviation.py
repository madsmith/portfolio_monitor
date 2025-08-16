from collections import deque
from statistics import mean
from datetime import datetime, timedelta

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class MovingAverageDeviationDetector(Detector):
    """Detector for price deviations from moving average"""
    
    @property
    def name(self) -> str:
        return "moving_average_deviation"
    
    def __init__(self, period: int = 60, threshold: float = 0.05):
        """
        Args:
            period: Number of samples for the moving average calculation (default: 60 samples)
            threshold: Deviation from MA that triggers an alert
        """
        self.period = period
        self.threshold = threshold
        self.price_histories: dict[AssetSymbol, deque[float]] = {}
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        symbol = aggregate.symbol
        # Initialize history for this ticker if it doesn't exist
        if symbol not in self.price_histories:
            self.price_histories[symbol] = deque(maxlen=self.period)
            
        # Add current close to history
        self.price_histories[symbol].append(aggregate.close)
        
        # Need enough history to calculate MA
        if len(self.price_histories[symbol]) < self.period:
            return None
            
        # Calculate moving average
        moving_avg = mean(self.price_histories[symbol])
        
        # Calculate percent deviation from moving average
        deviation_pct = (aggregate.close - moving_avg) / moving_avg
        
        # Check if deviation exceeds threshold
        if abs(deviation_pct) >= self.threshold:
            direction = "above" if deviation_pct > 0 else "below"
            msg = f"{symbol}: Price {direction} {self.period}-sample moving average by {abs(deviation_pct)*100:.2f}%"
            extra = {
                "deviation_percent": deviation_pct * 100,
            }
            
            return Alert(symbol, self.name, msg, extra, aggregate.date, aggregate)
            
        return None
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        The MovingAverageDeviationDetector needs period samples to calculate the moving average.
        """
        # Need period samples for the moving average
        required_samples = self.period
        
        # Calculate total time needed
        total_time_needed = sample_interval * required_samples
        
        return current_time - total_time_needed
