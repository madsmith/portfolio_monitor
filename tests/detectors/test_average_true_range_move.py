from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.average_true_range_move import AverageTrueRangeMoveDetector
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

TICKER = AssetSymbol("AAPL", AssetTypes.Stock)
BASE_TIME = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))

# ATR period used across all tests
PERIOD = 5


def make_agg(
    close: float,
    minute: int,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1000.0,
) -> Aggregate:
    return Aggregate(
        symbol=TICKER,
        date_open=BASE_TIME + timedelta(minutes=minute),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        timespan=timedelta(minutes=1),
    )


def feed_stable(detector: AverageTrueRangeMoveDetector, n: int = PERIOD) -> None:
    """Feed n stable candles with a range of 1.0 (high +0.5, low −0.5).

    With PERIOD=5, feeding 5 candles fills history to exactly ``period`` entries,
    which is the minimum needed to produce an ATR on the next update.
    """
    for i in range(n):
        detector.update(make_agg(100.0, i, high=100.5, low=99.5))


class TestAverageTrueRangeMoveDetector:
    def test_no_alert_insufficient_data(self):
        # Fewer than period+1 candles → no alert
        detector = AverageTrueRangeMoveDetector(period=PERIOD, threshold=2.0)
        for i in range(PERIOD):
            detector.update(make_agg(100.0, i, high=101.0, low=99.0))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_small_range(self):
        detector = AverageTrueRangeMoveDetector(period=PERIOD, threshold=2.0)
        feed_stable(detector)
        # Range of 1.0 equals ATR — ratio = 1.0, below the 2× threshold
        detector.update(make_agg(100.0, PERIOD, high=100.5, low=99.5))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_rising(self):
        """Upward candle with range >> ATR triggers alert (rising direction).

        Stable baseline ATR ≈ 1.0 (H−L = 1.0 each candle).
        Trigger candle: high=115, low=100 → range=15, multiple=15× > 2×.
        """
        detector = AverageTrueRangeMoveDetector(period=PERIOD, threshold=2.0)
        feed_stable(detector)
        detector.update(make_agg(114.0, PERIOD, high=115.0, low=100.0))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "average_true_range_move"
        assert alert.ticker == TICKER
        assert alert.extra["range_multiple"] >= 2.0
        assert alert.extra["current_range"] == 15.0

    def test_fires_falling(self):
        """Downward candle with range >> ATR triggers alert (falling direction).

        Stable baseline ATR ≈ 1.0.
        Trigger candle: high=101, low=86 → range=15, multiple=15× > 2×.
        """
        detector = AverageTrueRangeMoveDetector(period=PERIOD, threshold=2.0)
        feed_stable(detector)
        detector.update(make_agg(87.0, PERIOD, high=101.0, low=86.0))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "average_true_range_move"
        assert alert.ticker == TICKER
        assert alert.extra["range_multiple"] >= 2.0
        assert alert.extra["current_range"] == 15.0
