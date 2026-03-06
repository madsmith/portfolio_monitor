from dataclasses import dataclass
from datetime import datetime, timedelta
from portfolio_monitor.core.datetime import parse_period
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.detectors import DetectorRegistry
from portfolio_monitor.detectors.base import DetectorBase
from portfolio_monitor.service.types import AssetSymbol


@dataclass
class PreviousClose:
    date: datetime
    close: float


@DetectorRegistry.register
class PercentChangeDetector(DetectorBase):
    @property
    def name(self) -> str:
        return "percent_change"

    def __init__(self, threshold: float = 0.03, period: str = "1d") -> None:
        super().__init__()
        self.threshold = threshold
        self.period = period
        self._period_delta: timedelta = parse_period(period)
        self._price_history: dict[AssetSymbol, list[PreviousClose]] = {}

    def is_primed(self, symbol: AssetSymbol) -> bool:
        return (
            symbol not in self._priming_symbols
            and len(self._price_history.get(symbol, [])) >= 2
        )

    def update(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        self._append_price_history(aggregate)
        prev_close = self._get_reference_close(aggregate)
        if prev_close is None:
            return

        pct = (aggregate.close - prev_close) / prev_close
        if abs(pct) >= self.threshold:
            reference_label = (
                "previous session close" if self.period == "1d" else f"{self.period} ago"
            )
            msg = (
                f"{symbol}: {pct * 100:.2f}% vs previous close "
                f"({prev_close:.4f}) [{reference_label}]"
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
        if symbol not in self._price_history:
            self._price_history[symbol] = []

        self._price_history[symbol].append(
            PreviousClose(aggregate.date_open, aggregate.close)
        )
        self._cleanup_price_history(symbol)

    def _cleanup_price_history(self, symbol: AssetSymbol) -> None:
        if len(self._price_history[symbol]) <= 1:
            return

        current_close = self._price_history[symbol][-1]
        cutoff_date = current_close.date - self._period_delta

        prune_idx = -1

        for i in range(len(self._price_history[symbol]) - 1):
            pc = self._price_history[symbol][i]
            next_pc = self._price_history[symbol][i + 1]

            if pc.date > cutoff_date:
                break

            pruned_period = current_close.date - next_pc.date
            if pruned_period < self._period_delta:
                break

            prune_idx = i

        if prune_idx == -1:
            return

        self._price_history[symbol] = self._price_history[symbol][prune_idx:]

    def _get_reference_close(self, aggregate: Aggregate) -> float | None:
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

    async def prime(
        self,
        symbol: AssetSymbol,
        data_provider: DataProvider,
        current_time: datetime,
        sample_interval: timedelta,
    ) -> None:
        self._priming_symbols.add(symbol)
        try:
            from_ = current_time - self._period_delta - sample_interval
            aggs: list[Aggregate] = await data_provider.get_range(symbol, from_, current_time, cache_write=True)
            for agg in aggs:
                self.update(agg)
        finally:
            self._priming_symbols.discard(symbol)
