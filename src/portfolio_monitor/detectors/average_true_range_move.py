from collections import deque
from datetime import timedelta
import logging

from portfolio_monitor.data import Aggregate
from portfolio_monitor.detectors import DetectorRegistry
from portfolio_monitor.detectors.base import DetectorBase
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

@DetectorRegistry.register
class AverageTrueRangeMoveDetector(DetectorBase):
    """Detector for price moves that exceed a multiple of Average True Range"""

    @classmethod
    def name(cls) -> str:
        return "average_true_range_move"

    def __init__(self, samples: int = 30, threshold: float = 2.0) -> None:
        super().__init__()
        self.samples = samples
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
        return len(self.price_histories.get(symbol, [])) > self.samples

    def prime_age(self) -> timedelta | int:
        return self.samples + 6

    def update(self, aggregate: Aggregate) -> None:
        symbol = aggregate.symbol
        if symbol not in self.price_histories:
            self.price_histories[symbol] = deque(maxlen=self.samples + 1)

        self.price_histories[symbol].append(
            (aggregate.high, aggregate.low, aggregate.close)
        )

        if len(self.price_histories[symbol]) <= self.samples:
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
                f"Average True Range ({self.samples}-sample)"
            )
            extra = {
                "current_range": current_range,
                "average_true_range": atr,
                "range_multiple": atr_multiple,
            }
            self._fire_or_update_alert(symbol, msg, extra, aggregate)
        else:
            self._clear_alert(symbol)

