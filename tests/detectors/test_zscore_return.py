from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.zscore_return import ZScoreReturnDetector
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

TICKER = AssetSymbol("AAPL", AssetTypes.Stock)
BASE_TIME = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))


def make_agg(close: float, minute: int, *, volume: float = 1000.0) -> Aggregate:
    return Aggregate(
        symbol=TICKER,
        date_open=BASE_TIME + timedelta(minutes=minute),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        timespan=timedelta(minutes=1),
    )


def feed_alternating(detector: ZScoreReturnDetector, n: int = 9) -> None:
    """Feed alternating 100/101 prices to build a return history with non-zero std dev.

    The alternating pattern produces returns of roughly ±1% each step, giving
    a mean return near zero and a std dev of ~0.01, which is used to scale
    the trigger candles in the rising/falling tests.
    """
    for i in range(n):
        price = 100.0 if i % 2 == 0 else 101.0
        detector.update(make_agg(price, i))


class TestZScoreReturnDetector:
    def test_no_alert_insufficient_data(self):
        detector = ZScoreReturnDetector(period="30m", threshold=2.0)
        # Fewer than 3 candles → returns array too short
        detector.update(make_agg(100.0, 0))
        alert = detector.update(make_agg(100.0, 1))
        assert alert is None

    def test_no_alert_zero_std_dev(self):
        detector = ZScoreReturnDetector(period="30m", threshold=2.0)
        # All identical prices → all returns = 0, std dev = 0 → no alert
        for i in range(10):
            alert = detector.update(make_agg(100.0, i))
        assert alert is None

    def test_no_alert_small_return(self):
        detector = ZScoreReturnDetector(period="30m", threshold=2.0)
        feed_alternating(detector)
        # Return of ~1% is within the normal ±1% range (z_score ≈ 1 < 2)
        alert = detector.update(make_agg(101.0, 9))
        assert alert is None

    def test_fires_rising(self):
        """Large positive return exceeds z-score threshold (rising direction)."""
        detector = ZScoreReturnDetector(period="30m", threshold=2.0)
        feed_alternating(detector)
        # Previous close is 100.0 (minute 8); return = (120−100)/100 = 20%
        # With std_dev ≈ 0.01, z_score ≈ 20 >> 2 → fires
        alert = detector.update(make_agg(120.0, 9))
        assert alert is not None
        assert alert.kind == "zscore_return"
        assert alert.ticker == TICKER
        assert "above" in alert.message
        assert alert.extra["z_score"] > 2.0
        assert alert.extra["current_return_percent"] > 0.0

    def test_fires_falling(self):
        """Large negative return exceeds z-score threshold (falling direction)."""
        detector = ZScoreReturnDetector(period="30m", threshold=2.0)
        feed_alternating(detector)
        # Previous close is 100.0 (minute 8); return = (80−100)/100 = −20%
        # z_score ≈ −20 → abs >= 2 → fires with negative z_score
        alert = detector.update(make_agg(80.0, 9))
        assert alert is not None
        assert alert.kind == "zscore_return"
        assert alert.ticker == TICKER
        assert "below" in alert.message
        assert alert.extra["z_score"] < -2.0
        assert alert.extra["current_return_percent"] < 0.0
