from collections import deque
from datetime import datetime, timedelta
import logging

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.detectors import DetectorRegistry
from portfolio_monitor.detectors.base import DetectorBase
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

@DetectorRegistry.register
class AverageTrueRangeMoveDetector(DetectorBase):
    """Detector for price moves that exceed a multiple of Average True Range"""

    @property
    def name(self) -> str:
        return "average_true_range_move"

    def __init__(self, period: int = 30, threshold: float = 2.0) -> None:
        super().__init__()
        self.period = period
        self.threshold_multiple = threshold
        self.price_histories: dict[AssetSymbol, deque[tuple[float, float, float]]] = {}

    def _calculate_atr(self, price_history: deque[tuple[float, float, float]]) -> float:
        if len(price_history) <= 1:
            return 0.0
        true_ranges = []
        for i in range(1, len(price_history)):
            prev_close = price_history[i - 1][2]
            high, low, _ = price_history[i]
            true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(true_range)
        return sum(true_ranges) / len(true_ranges)

    def is_primed(self, symbol: AssetSymbol) -> bool:
        return (
            symbol not in self._priming_symbols
            and len(self.price_histories.get(symbol, [])) > self.period
        )

    def update(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        if symbol not in self.price_histories:
            self.price_histories[symbol] = deque(maxlen=self.period + 1)

        self.price_histories[symbol].append(
            (aggregate.high, aggregate.low, aggregate.close)
        )

        if len(self.price_histories[symbol]) <= self.period:
            return

        atr = self._calculate_atr(self.price_histories[symbol])
        if atr == 0:
            self._clear_alert(symbol)
            return

        current_range = aggregate.high - aggregate.low

        if current_range >= (atr * self.threshold_multiple):
            atr_multiple = current_range / atr
            msg = (
                f"{symbol}: Range of {current_range:.2f} is {atr_multiple:.2f}x "
                f"Average True Range ({self.period}-sample)"
            )
            extra = {
                "current_range": current_range,
                "average_true_range": atr,
                "range_multiple": atr_multiple,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)

    async def prime(
        self,
        symbol: AssetSymbol,
        data_provider: DataProvider,
        current_time: datetime,
        sample_interval: timedelta,
    ) -> None:
        self._priming_symbols.add(symbol)
        try:
            # Need period+6 samples (period for ATR + buffer)
            required_time = sample_interval * (self.period + 6)
            from_ = current_time - required_time
            logger.debug("Prime Range for %s (%s): %d minutes", self.name, symbol, int((current_time - from_).total_seconds() / 60))
            aggs: list[Aggregate] = await data_provider.get_range(symbol, from_, current_time, cache_write=True)
            for agg in aggs:
                self.update(agg)
        finally:
            self._priming_symbols.discard(symbol)
