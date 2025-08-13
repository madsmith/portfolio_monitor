from collections import deque
from statistics import mean

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class MovingAverageDeviationDetector(Detector):
    """Detector for price deviations from moving average"""
    
    @property
    def name(self) -> str:
        return "moving_average_deviation"
    
    def __init__(self, period: int = 60, threshold_pct: float = 0.05):
        """
        Args:
            period: Number of samples for the moving average calculation (default: 60 samples)
            threshold_pct: Percent deviation from MA that triggers an alert (0.05 = 5%)
        """
        self.period = period
        self.threshold_pct = threshold_pct
        self.price_histories: dict[AssetSymbol, deque[float]] = {}
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        ticker = aggregate.symbol
        # Initialize history for this ticker if it doesn't exist
        if ticker not in self.price_histories:
            self.price_histories[ticker] = deque(maxlen=self.period)
            
        # Add current close to history
        self.price_histories[ticker].append(aggregate.close)
        
        # Need enough history to calculate MA
        if len(self.price_histories[ticker]) < self.period:
            return None
            
        # Calculate moving average
        moving_avg = mean(self.price_histories[ticker])
        
        # Calculate percent deviation from moving average
        deviation_pct = (aggregate.close - moving_avg) / moving_avg
        
        # Check if deviation exceeds threshold
        if abs(deviation_pct) >= self.threshold_pct:
            direction = "above" if deviation_pct > 0 else "below"
            msg = f"{ticker}: Price {direction} {self.period}-sample moving average by {abs(deviation_pct)*100:.2f}%"
            
            return Alert(ticker, self.name, abs(deviation_pct), msg, aggregate.date, aggregate)
            
        return None
