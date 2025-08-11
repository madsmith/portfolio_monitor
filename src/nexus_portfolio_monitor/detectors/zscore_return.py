from collections import deque
from statistics import mean, stdev

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector


class ZScoreReturnDetector(Detector):
    """Detector for returns that deviate significantly from historical distribution"""
    
    def __init__(self, lookback_period: int = 60, zscore_threshold: float = 2.0):
        """
        Args:
            lookback_period: Number of samples to establish the return distribution (default: 60 samples)
            zscore_threshold: Z-score threshold that triggers an alert
        """
        self.lookback_period = lookback_period
        self.zscore_threshold = zscore_threshold
        # Dictionary of price history per ticker
        self.close_histories: dict[str, deque[float]] = {}
        
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
        
    def update(self, ticker: str, aggregate: Aggregate) -> Alert | None:
        # Initialize history for this ticker if it doesn't exist
        if ticker not in self.close_histories:
            self.close_histories[ticker] = deque(maxlen=self.lookback_period + 1)  # +1 to calculate returns
            
        # Add current close to history
        self.close_histories[ticker].append(aggregate.close)
        
        # Need enough history to calculate meaningful statistics
        if len(self.close_histories[ticker]) <= self.lookback_period:
            return None
            
        returns = self._calculate_returns(self.close_histories[ticker])
        
        # Need at least a few returns to calculate statistics
        if len(returns) < 5:
            return None
            
        # Calculate today's return
        yesterday_close = list(self.close_histories[ticker])[-2]
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
        if abs(zscore) >= self.zscore_threshold:
            direction = "positive" if zscore > 0 else "negative"
            msg = f"{ticker}: {direction} return with z-score of {zscore:.2f} (±{self.zscore_threshold} threshold)"
            
            return Alert(ticker, "zscore_return", abs(zscore), msg, aggregate.date)
            
        return None
