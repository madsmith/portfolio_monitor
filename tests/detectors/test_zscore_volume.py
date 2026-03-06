from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.zscore_volume import ZScoreVolumeDetector
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


def feed_alternating(detector: ZScoreVolumeDetector, n: int = 9) -> None:
    """Feed alternating 1100/900 volumes to build history with non-zero std dev (~100)."""
    for i in range(n):
        vol = 1100.0 if i % 2 == 0 else 900.0
        detector.update(make_agg(100.0, i, volume=vol))


class TestZScoreVolumeDetector:
    def test_no_alert_insufficient_data(self):
        detector = ZScoreVolumeDetector(period="30m", threshold=1.0)
        # Single candle: std dev = 0 (not enough history)
        detector.update(make_agg(100.0, 0, volume=1000.0))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_zero_std_dev(self):
        detector = ZScoreVolumeDetector(period="30m", threshold=1.0)
        # All identical volumes → std dev = 0 → no alert
        for i in range(10):
            detector.update(make_agg(100.0, i, volume=1000.0))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_below_threshold(self):
        detector = ZScoreVolumeDetector(period="30m", threshold=1.0)
        feed_alternating(detector)
        # Volume of 1050 is slightly above mean (~1015), z_score ≈ 0.35 < 1.0
        detector.update(make_agg(100.0, 9, volume=1050.0))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_rising(self):
        """Volume spike well above mean triggers alert (rising direction)."""
        detector = ZScoreVolumeDetector(period="30m", threshold=1.0)
        feed_alternating(detector)
        # With baseline std_dev ≈ 100, volume of 5000 gives z_score >> 1
        detector.update(make_agg(100.0, 9, volume=5000.0))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "zscore_volume"
        assert alert.ticker == TICKER
        assert "above" in alert.message
        assert alert.extra["z_score"] > 1.0
        assert alert.extra["current_volume"] == 5000.0

    def test_no_alert_falling_volume(self):
        """Volume drop below baseline does not trigger (detector only fires on spikes)."""
        detector = ZScoreVolumeDetector(period="30m", threshold=1.0)
        feed_alternating(detector)
        # Volume collapses to 100 → z_score << 0, no alert
        detector.update(make_agg(100.0, 9, volume=100.0))
        assert detector.get_current_alert(TICKER) is None
