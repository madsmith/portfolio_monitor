from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.percent_change import (
    PercentChangeDetector,
    PercentChangeFromPreviousCloseDetector,
)
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


# ---------------------------------------------------------------------------
# PercentChangeFromPreviousCloseDetector
# ---------------------------------------------------------------------------


class TestPercentChangeFromPreviousCloseDetector:
    def test_no_alert_first_candle(self):
        detector = PercentChangeFromPreviousCloseDetector(threshold=0.03)
        # First candle stores the price but has no previous reference
        alert = detector.update(make_agg(100.0, 0))
        assert alert is None

    def test_no_alert_below_threshold(self):
        detector = PercentChangeFromPreviousCloseDetector(threshold=0.03)
        detector.update(make_agg(100.0, 0))
        # 1% change — below the 3% threshold
        alert = detector.update(make_agg(101.0, 1))
        assert alert is None

    def test_fires_rising(self):
        """Price rise above threshold triggers alert (rising direction)."""
        detector = PercentChangeFromPreviousCloseDetector(threshold=0.03)
        detector.update(make_agg(100.0, 0))
        # +4% change — above the 3% threshold
        alert = detector.update(make_agg(104.0, 1))
        assert alert is not None
        assert alert.kind == "percent_change_previous_close"
        assert alert.ticker == TICKER
        assert alert.extra["percent_change"] > 0.0
        assert alert.extra["percent_change"] > 3.0

    def test_fires_falling(self):
        """Price drop below threshold triggers alert (falling direction)."""
        detector = PercentChangeFromPreviousCloseDetector(threshold=0.03)
        detector.update(make_agg(100.0, 0))
        # −4% change — below negative threshold
        alert = detector.update(make_agg(96.0, 1))
        assert alert is not None
        assert alert.kind == "percent_change_previous_close"
        assert alert.ticker == TICKER
        assert alert.extra["percent_change"] < 0.0
        assert alert.extra["percent_change"] < -3.0


# ---------------------------------------------------------------------------
# PercentChangeDetector
# ---------------------------------------------------------------------------


class TestPercentChangeDetector:
    def test_no_alert_first_candle(self):
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        alert = detector.update(make_agg(100.0, 0))
        assert alert is None

    def test_no_alert_below_threshold(self):
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(100.0, 0))
        # 1% change vs oldest reference — below threshold
        alert = detector.update(make_agg(101.0, 1))
        assert alert is None

    def test_fires_rising(self):
        """Price rise above threshold vs period reference triggers alert (rising direction).

        With period="5m" and two candles 1 minute apart, the oldest entry
        (t=0, close=100) is within the window and used as the reference.
        Change = (104−100)/100 = 4% > 3% → fires.
        """
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(100.0, 0))
        alert = detector.update(make_agg(104.0, 1))
        assert alert is not None
        assert alert.kind == "percent_change"
        assert alert.ticker == TICKER
        assert alert.extra["percent_change"] > 0.0
        assert alert.extra["percent_change"] > 3.0

    def test_fires_falling(self):
        """Price drop below threshold vs period reference triggers alert (falling direction).

        Change = (96−100)/100 = −4% → abs > 3% → fires.
        """
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(100.0, 0))
        alert = detector.update(make_agg(96.0, 1))
        assert alert is not None
        assert alert.kind == "percent_change"
        assert alert.ticker == TICKER
        assert alert.extra["percent_change"] < 0.0
        assert alert.extra["percent_change"] < -3.0
