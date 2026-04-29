from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from portfolio_monitor.core import parse_period
from portfolio_monitor.data import Aggregate, MarketInfo
from portfolio_monitor.detectors import DetectorRegistry
from portfolio_monitor.detectors.base import DetectorBase
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

@dataclass
class PreviousClose:
    date: datetime
    close: float


@DetectorRegistry.register
class PercentChangeDetector(DetectorBase):
    @classmethod
    def name(cls) -> str:
        return "percent_change"


    def __init__(self, threshold: float = 0.03, period: str = "1d") -> None:
        super().__init__()
        self.threshold = threshold
        self.period = period
        self._period_delta: timedelta = parse_period(period)
        self._price_history: defaultdict[AssetSymbol, list[PreviousClose]] = defaultdict(list)
        self._is_primed: defaultdict[AssetSymbol, bool] = defaultdict(bool)


    def is_primed(self, symbol: AssetSymbol) -> bool:
        return self._is_primed[symbol]


    def prime_age(self) -> timedelta | int:
        return self._period_delta


    def update(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        self._append_price_history(aggregate)

        prev_close = self._get_reference_close(aggregate)
        if prev_close is None:
            return
        
        # Check if the aggregate marks us as primed
        if not self.is_primed(symbol):
            current_close = aggregate.date_open + aggregate.timespan

            if prev_close.date <= current_close - self._period_delta:
                self._is_primed[symbol] = True

        # Check alert conditions
        pct = (aggregate.close - prev_close.close) / prev_close.close
        if abs(pct) >= self.threshold:
            reference_label = (
                "previous session close" if self.period == "1d" else f"{self.period} ago"
            )
            msg = (
                f"{symbol}: {pct * 100:.2f}% vs previous close "
                f"({prev_close.close:.4f}) [{reference_label}]"
            )
            extra = {"percent_change": pct * 100}

            current = self.get_current_alert(symbol)

            if current is None:
                self._start_alert(symbol, msg, extra, aggregate)
            elif (current.extra["percent_change"] > 0) != (pct > 0):
                # Direction flipped — clear old occurrence, start fresh
                self._clear_alert(symbol)
                self._start_alert(symbol, msg, extra, aggregate)
            else:
                self._update_current_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)


    def _append_price_history(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol

        self._price_history[symbol].append(
            PreviousClose(aggregate.date_open + aggregate.timespan, aggregate.close)
        )

        self._cleanup_price_history(symbol)


    def _cleanup_price_history(self, symbol: AssetSymbol) -> None:
        if len(self._price_history[symbol]) <= 1:
            return

        current_close = self._price_history[symbol][-1]
        cutoff_date =  self._get_reference_close_datetime(symbol, current_close.date)
        if cutoff_date is None:
            logger.warning("Could not determine cutoff date for symbol %s at %s - Cleanup Aborted", symbol, current_close.date)
            return
        
        self._price_history[symbol] = [price_close for price_close in self._price_history[symbol] if price_close.date >= cutoff_date]


    def _get_reference_close_datetime(self, symbol: AssetSymbol, date: datetime) -> datetime | None:
        if self.period == "1d":
            value = MarketInfo.get_previous_market_close(symbol, date)
            return value
        else:
            return date - self._period_delta


    def _get_reference_close(self, aggregate: Aggregate) -> PreviousClose | None:
        symbol = aggregate.symbol
        history = self._price_history.get(symbol)
        if not history or len(history) < 2:
            return None

        if self.period == "1d":
            reference_datetime = self._get_reference_close_datetime(symbol, aggregate.date_open + aggregate.timespan)
            if reference_datetime is None:
                logger.warning("Could not determine reference close for symbol %s at %s", symbol, aggregate.date_open)
                return None
            
            # Hack - Some API's return invalid open time for previous close aggregates, leading to off by one issues
            # We will accept a PreviousClose 1 min after close as also valid.
            reference_datetime = reference_datetime + timedelta(minutes=1)
            reference: PreviousClose | None = None
            for price_close in history:
                if price_close.date <= reference_datetime:
                    reference = price_close
                else:
                    break
            return reference

        return history[0]
