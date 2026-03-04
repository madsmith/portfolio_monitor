from dataclasses import dataclass
from datetime import datetime, timedelta

from portfolio_monitor.core.datetime import parse_period
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.detectors import Alert, Detector, DetectorRegistry
from portfolio_monitor.service.types import AssetSymbol


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
            reference_label = "previous session close" if self.period == "1d" else f"{self.period} ago"
            msg = f"{symbol}: {pct * 100:.2f}% vs previous close ({prev_close:.4f}) [{reference_label}]"
            extra = {"percent_change": pct * 100}
            return Alert(symbol, self.name, msg, extra, aggregate.date_open, aggregate)
        return None

    def _append_price_history(self, aggregate: Aggregate) -> None:
        """
        Append the previous close price for the set period to the list of previous closes.
        Any prices older than the set period are removed.
        """
        symbol = aggregate.symbol
        if symbol not in self._price_history:
            self._price_history[symbol] = []

        self._price_history[symbol].append(
            PreviousClose(aggregate.date_open, aggregate.close)
        )

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
            next_pc = self._price_history[symbol][i + 1]

            # Is this price eligible? If not, done
            if pc.date > cutoff_date:
                break

            # Ensure remaining period is at least the set period
            pruned_period = current_close.date - next_pc.date
            if pruned_period < period_timedelta:
                break  # Can't prune, not enought remaining period

            prune_idx = i

        # Validate prune idx
        if prune_idx == -1:
            return

        # Prune the price history
        self._price_history[symbol] = self._price_history[symbol][prune_idx:]

    def _get_reference_close(self, aggregate: Aggregate) -> float | None:
        """
        For the given ticker, return the reference close price.

        For period="1d", uses MarketInfo to find the actual previous session close
        datetime and returns the most recent history entry at or before that boundary.
        For all other periods, returns the oldest entry in the rolling window.
        """
        symbol = aggregate.symbol
        history = self._price_history.get(symbol)
        if not history or len(history) < 2:
            return None

        if self.period == "1d":
            prev_session_close = MarketInfo.get_previous_market_close(symbol, aggregate.date_open)
            reference: PreviousClose | None = None
            for pc in history:
                if pc.date <= prev_session_close:
                    reference = pc
                else:
                    break
            return reference.close if reference is not None else None

        return history[0].close

    def preload_data_age(
        self, current_time: datetime, sample_interval: timedelta
    ) -> datetime | None:
        """
        This detector needs data going back to the specified period.
        """
        # Need data as old as the period
        period_td = parse_period(self.period)

        # Add a buffer of one sample interval to ensure we have data beyond the period
        buffer = sample_interval

        return current_time - period_td - buffer
