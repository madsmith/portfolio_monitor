from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class PercentChangeFromPreviousCloseDetector(Detector):
    @property
    def name(self) -> str:
        return "percent_change"
        
    def __init__(self, threshold_pct: float = 0.03):
        """Detector for significant percentage changes from previous close price
        
        Args:
            threshold_pct: Percent change threshold that triggers an alert (default: 0.03 for 3%)
        """
        self.threshold_pct = threshold_pct
        self.previous_closes: dict[AssetSymbol, float] = {}

    def update(self, aggregate: Aggregate) -> Alert | None:
        ticker = aggregate.symbol
        if ticker not in self.previous_closes:
            self.previous_closes[ticker] = aggregate.close
            return None
        
        prev_close = self.previous_closes[ticker]
        pct = (aggregate.close - prev_close) / prev_close
        
        # Update previous close for next time
        self.previous_closes[ticker] = aggregate.close
        
        if abs(pct) >= self.threshold_pct:
            msg = f"{ticker}: {pct*100:.2f}% vs prev close ({prev_close:.4f})"
            return Alert(ticker, self.name, abs(pct), msg, aggregate.date, aggregate)
        return None