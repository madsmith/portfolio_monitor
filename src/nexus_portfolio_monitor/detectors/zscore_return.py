import numpy as np

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, HistoryRecord, TimeRangeDetectorBase, DetectorRegistry

@DetectorRegistry.register
class ZScoreReturnDetector(TimeRangeDetectorBase[float]):
    """
    Detector for returns that deviate significantly from historical distribution.
    
    This detector tracks asset price movements over a specified time period and alerts
    when the current price movement (return) deviates significantly from the historical
    distribution of returns, measured in standard deviations (Z-score).
    """
    
    @property
    def name(self) -> str:
        return "zscore_return"
    
    def __init__(self, period: str = "2h", threshold: float = 2.0):
        """
        Initialize the Z-score return detector with specified parameters.
        
        Args:
            period: Time period to use for calculating return statistics (e.g. "2h", "1d").
                    Used for establishing the baseline return distribution.
            threshold: Z-score threshold that triggers an alert (e.g. 2.0 means
                return must be at least 2 standard deviations from the mean).
        """
        super().__init__(period)
        self.threshold = threshold

    def _value_from_aggregate(self, aggregate: Aggregate) -> float:
        return aggregate.close

    def _check_alert(self, aggregate: Aggregate) -> Alert | None:
        close_history = self.histories[aggregate.symbol]

        if len(close_history) < 2:
            return None
        
        return_values = self._calculate_returns(close_history)

        previous_close = close_history[-2].value
        current_return = (aggregate.close - previous_close) / previous_close
        mean_return = np.mean(return_values)
        std_dev = np.std(return_values)
        z_score = (current_return - mean_return) / std_dev

        if np.abs(z_score) >= self.threshold:
            msg = f"{aggregate.symbol}: Return of {current_return:.2f} is {z_score:.2f} standard deviations over {self.period} average"
            extra = {
                "z_score": z_score,
                "current_return": current_return,
                "average_return": mean_return,
                "standard_deviation": std_dev,
            }
            return Alert(aggregate.symbol, self.name, msg, extra, aggregate.date, aggregate)
    
    def _calculate_returns(self, close_history: list[HistoryRecord[float]]) -> list[float]:
        """Calculate percentage returns from price history"""
        if len(close_history) <= 1:
            return []
            
        returns = []
        prices = [record.value for record in close_history]
        
        for i in range(1, len(prices)):
            return_value = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(return_value)
            
        return returns