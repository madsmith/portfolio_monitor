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
        detector.update(make_agg(100.0, 0, volume=1000.0))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_below_threshold(self):
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        # Volume at 1.5× mean — below the 2× threshold
        # mean = (9×1000 + 1500) / 10 = 1050  →  1500 < 1050×2 = 2100
        detector.update(make_agg(100.0, 9, volume=1500.0))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_rising(self):
        """Volume spike well above threshold triggers alert."""
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        # mean = (9×1000 + 5000) / 10 = 1400  →  5000 ≥ 1400×2 = 2800
        detector.update(make_agg(100.0, 9, volume=5000.0))
        alert = detector.get_current_alert(TICKER)
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
        detector.update(make_agg(100.0, 9, volume=100.0))
        assert detector.get_current_alert(TICKER) is None

    def test_update_preserves_id(self):
        """Consecutive spikes update the same alert occurrence."""
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        detector.update(make_agg(100.0, 9, volume=5000.0))
        first_id = detector.get_current_alert(TICKER).id  # type: ignore[union-attr]

        detector.update(make_agg(100.0, 10, volume=6000.0))
        assert detector.get_current_alert(TICKER).id == first_id  # type: ignore[union-attr]

    def test_clears_when_condition_ends(self):
        """Alert clears when volume returns to normal."""
        detector = VolumeSpikeDetector(period="30m", threshold=2.0)
        feed_baseline(detector, 9)
        detector.update(make_agg(100.0, 9, volume=5000.0))
        assert detector.get_current_alert(TICKER) is not None
        detector.update(make_agg(100.0, 10, volume=1000.0))
        assert detector.get_current_alert(TICKER) is None
