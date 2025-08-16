from dataclasses import dataclass
from datetime import datetime, timedelta
from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.core.datetime import parse_period
from nexus_portfolio_monitor.detectors.base import Alert, Detector, DetectorRegistry
from nexus_portfolio_monitor.service.types import AssetSymbol


@DetectorRegistry.register
class PercentChangeFromPreviousCloseDetector(Detector):
    @property
    def name(self) -> str:
        return "percent_change_previous_close"
        
    def __init__(self, threshold: float = 0.03):
        """Detector for significant percentage changes from previous close price
        
        Args:
            threshold: Percent change threshold that triggers an alert (default: 0.03 for 3%)
        """
        self.threshold = threshold
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
        
        if abs(pct) >= self.threshold:
            msg = f"{ticker}: {pct*100:.2f}% vs previous close ({prev_close:.4f})"
            return Alert(ticker, self.name, abs(pct), msg, aggregate.date, aggregate)
        return None
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        This detector only needs one previous data point to function.
        """
        # Need one previous data point
        return current_time - sample_interval

@dataclass
class PreviousClose:
    date: datetime
    close: float

@DetectorRegistry.register
class PercentChangeDetector(Detector):
    @property
    def name(self) -> str:
        return "percent_change"

    def __init__(self, threshold: float = 0.03, period: str = "1d"):
        """Detector for significant percentage changes from previous close price
        
        Args:
            threshold: Percent change threshold that triggers an alert (default: 0.03 for 3%)
            period: Period to calculate the percentage change (default: "1d")
        """
        self.threshold = threshold
        self.period = period

        self._price_history: dict[AssetSymbol, list[PreviousClose]] = {}
        
    def update(self, aggregate: Aggregate) -> Alert | None:
        symbol = aggregate.symbol
        self._append_price_history(aggregate)
        prev_close = self._get_reference_close(aggregate)
        if prev_close is None:
            return None

        pct = (aggregate.close - prev_close) / prev_close
        if abs(pct) >= self.threshold:
            msg = f"{symbol}: {pct*100:.2f}% vs previous close ({prev_close:.4f}) [{self.period} ago]"
            return Alert(symbol, self.name, abs(pct), msg, aggregate.date, aggregate)
        return None
        
    def _append_price_history(self, aggregate: Aggregate) -> None:
        """
        Append the previous close price for the set period to the list of previous closes.
        Any prices older than the set period are removed.
        """
        symbol = aggregate.symbol
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        
        self._price_history[symbol].append(PreviousClose(aggregate.date, aggregate.close))

        self._cleanup_price_history(symbol)

    def _cleanup_price_history(self, symbol: AssetSymbol) -> None:
        """
        Remove any prices older than the set period.
        """
        if len(self._price_history[symbol]) <= 1:
            return

        current_close = self._price_history[symbol][-1]
        period_timedelta = parse_period(self.period)
        cutoff_date = current_close.date - period_timedelta

        prune_idx = -1

        # Walk through each item advancing prune idx if
        # 1) data is older than the cutoff date
        # 2) remaining period would not be less than the set period
        for i in range(len(self._price_history[symbol]) - 1):
            pc = self._price_history[symbol][i]
            next_pc = self._price_history[symbol][i+1]

            # Is this price eligible? If not, done
            if pc.date > cutoff_date:
                break
            
            # Ensure remaining period is at least the set period
            pruned_period = current_close.date - next_pc.date
            if pruned_period < period_timedelta:
                break # Can't prune, not enought remaining period

            prune_idx = i
            
        # Validate prune idx
        if prune_idx == -1:
            return
        
        # Prune the price history
        self._price_history[symbol] = self._price_history[symbol][prune_idx:]

    def _get_reference_close(self, aggregate: Aggregate) -> float | None:
        """
        For the given ticker, return the previous close price for the set period.
        """
        symbol = aggregate.symbol
        if symbol not in self._price_history:
            return None
        
        # Need at least 2 prices to calculate a percentage change
        if len(self._price_history[symbol]) < 2:
            return None
        
        oldest_close = self._price_history[symbol][0]
        return oldest_close.close
        
    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        This detector needs data going back to the specified period.
        """
        # Need data as old as the period
        period_td = parse_period(self.period)
        
        # Add a buffer of one sample interval to ensure we have data beyond the period
        buffer = sample_interval
        
        return current_time - period_td - buffer