from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.volume_spike import VolumeSpikeDetector
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


def feed_baseline(detector: VolumeSpikeDetector, n: int, volume: float = 1000.0) -> None:
    for i in range(n):
        detector.update(make_agg(100.0, i, volume=volume))


class TestVolumeSpikeDetector:
    def test_no_alert_insufficient_data(self):
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        # Single candle: volume == mean, ratio = 1 < threshold
        alert = detector.update(make_agg(100.0, 0, volume=1000.0))
        assert alert is None

    def test_no_alert_below_threshold(self):
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        # Volume at 1.5× mean — below the 2× threshold
        # mean = (9×1000 + 1500) / 10 = 1050  →  1500 < 1050×2 = 2100
        alert = detector.update(make_agg(100.0, 9, volume=1500.0))
        assert alert is None

    def test_fires_rising(self):
        """Volume spike well above threshold triggers alert (rising direction)."""
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        # mean = (9×1000 + 5000) / 10 = 1400  →  5000 ≥ 1400×2 = 2800
        alert = detector.update(make_agg(100.0, 9, volume=5000.0))
        assert alert is not None
        assert alert.kind == "volume_spike"
        assert alert.ticker == TICKER
        assert alert.extra["current_volume"] == 5000.0
        assert alert.extra["percent_increase"] > 0.0

    def test_no_alert_falling_volume(self):
        """Volume drop below baseline does not trigger (detector only fires on spikes)."""
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        # Volume collapses — well below the mean, cannot meet threshold
        alert = detector.update(make_agg(100.0, 9, volume=100.0))
        assert alert is None
