from collections import deque
from datetime import datetime, timedelta
from statistics import mean, stdev

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class ZScoreReturnDetector(Detector):
    """Detector for returns that deviate significantly from historical distribution"""
    
    @property
    def name(self) -> str:
        return "zscore_return"
    
    def __init__(self, lookback_period: int = 60, threshold: float = 2.0):
        """
        Args:
            lookback_period: Number of samples to establish the return distribution (default: 60 samples)
            threshold: Z-score threshold that triggers an alert
        """
        self.lookback_period = lookback_period
        self.threshold = threshold
        # Dictionary of price history per ticker
        self.close_histories: dict[AssetSymbol, deque[float]] = {}
        
    def _calculate_returns(self, close_history: deque[float]) -> list[float]:
        """Calculate percentage returns from price history"""
        if len(close_history) <= 1:
            return []
            
        returns = []
        prices = list(close_history)
        
        for i in range(1, len(prices)):
            pct_return = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(pct_return)
            
        return returns
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        symbol = aggregate.symbol
        # Initialize history for this ticker if it doesn't exist
        if symbol not in self.close_histories:
            self.close_histories[symbol] = deque(maxlen=self.lookback_period + 1)  # +1 to calculate returns
            
        # Add current close to history
        self.close_histories[symbol].append(aggregate.close)
        
        # Need enough history to calculate meaningful statistics
        if len(self.close_histories[symbol]) <= self.lookback_period:
            return None
            
        returns = self._calculate_returns(self.close_histories[symbol])
        
        # Need at least a few returns to calculate statistics
        if len(returns) < 5:
            return None
            
        # Calculate today's return
        yesterday_close = list(self.close_histories[symbol])[-2]
        today_return = (aggregate.close - yesterday_close) / yesterday_close
        
        # Calculate z-score of today's return
        returns_without_today = returns[:-1]
        avg_return = mean(returns_without_today)
        std_return = stdev(returns_without_today)
        
        # Avoid division by zero
        if std_return == 0:
            return None
            
        zscore = (today_return - avg_return) / std_return
        
        # Check if z-score exceeds threshold
        if abs(zscore) >= self.threshold:
            direction = "positive" if zscore > 0 else "negative"
            msg = f"{symbol}: {direction} return with z-score of {zscore:.2f} (±{self.threshold} threshold)"
            
            return Alert(symbol, self.name, abs(zscore), msg, aggregate.date, aggregate)
            
        return None
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        The ZScoreReturnDetector needs lookback_period + 1 samples to function effectively.
        """
        # Need lookback_period + 1 samples to have meaningful statistics
        required_samples = self.lookback_period + 1
        
        # Add a few more samples as buffer for statistical stability
        buffer_samples = 5
        
        # Calculate total time needed
        total_samples_needed = required_samples + buffer_samples
        total_time_needed = sample_interval * total_samples_needed
        
        return current_time - total_time_needed
