from collections import deque

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector


class AverageTrueRangeMoveDetector(Detector):
    """Detector for price moves that exceed a multiple of Average True Range"""
    
    @property
    def name(self) -> str:
        return "average_true_range_move"
    
    def __init__(self, period: int = 30, threshold_mult: float = 2.0):
        """
        Args:
            period: Number of samples to calculate ATR (default: 30 samples)
            threshold_mult: Multiple of ATR that triggers an alert
        """
        self.period = period
        self.threshold_mult = threshold_mult
        # Dictionary of price histories per ticker: [high, low, close]
        self.price_histories: dict[str, deque[tuple[float, float, float]]] = {}
        
    def _calculate_atr(self, price_history: deque[tuple[float, float, float]]) -> float:
        """Calculate the Average True Range"""
        if len(price_history) <= 1:
            return 0.0
            
        true_ranges = []
        
        for i in range(1, len(price_history)):
            prev_close = price_history[i-1][2]
            high, low, _ = price_history[i]
            
            # True range is the greatest of:
            # 1. Current high - current low
            # 2. Abs(current high - previous close)
            # 3. Abs(current low - previous close)
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            true_range = max(tr1, tr2, tr3)
            
            true_ranges.append(true_range)
            
        # Simple average of true ranges
        return sum(true_ranges) / len(true_ranges)
        
    def update(self, ticker: str, aggregate: Aggregate) -> Alert | None:
        # Initialize history for this ticker if it doesn't exist
        if ticker not in self.price_histories:
            self.price_histories[ticker] = deque(maxlen=self.period+1)  # +1 to calculate TR
            
        # Add current candle data to history
        self.price_histories[ticker].append((aggregate.high, aggregate.low, aggregate.close))
        
        # Need at least atr_period + 1 candles to calculate meaningful ATR
        if len(self.price_histories[ticker]) <= self.period:
            return None
            
        # Calculate ATR
        atr = self._calculate_atr(self.price_histories[ticker])
        if atr == 0:
            return None
            
        # Calculate today's range
        current_range = aggregate.high - aggregate.low
        
        # Check if current range exceeds ATR threshold
        if current_range >= (atr * self.threshold_mult):
            atr_multiple = current_range / atr
            msg = f"{ticker}: Range of {current_range:.2f} is {atr_multiple:.2f}x Average True Range ({self.period}-sample)"
            
            return Alert(ticker, self.name, atr_multiple, msg, aggregate.date, aggregate)
            
        return None
