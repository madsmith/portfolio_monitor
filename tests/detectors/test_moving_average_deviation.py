from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.moving_average_deviation import SMADeviationDetector
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


def feed_stable(detector: SMADeviationDetector, n: int, price: float = 100.0) -> None:
    for i in range(n):
        detector.update(make_agg(price, i))


class TestSMADeviationDetector:
    def test_no_alert_below_threshold(self):
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 9)
        # 1% rise — well below the 5% threshold
        alert = detector.update(make_agg(101.0, 9))
        assert alert is None

    def test_no_alert_insufficient_data(self):
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        # Single candle: price == mean, deviation = 0
        alert = detector.update(make_agg(100.0, 0))
        assert alert is None

    def test_fires_rising(self):
        """Price well above the SMA triggers an alert (rising direction)."""
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 9)
        # Price jumps ~15% above baseline → deviation ≈ 13.3% > 5%
        # mean = (9×100 + 115) / 10 = 101.5  →  |115−101.5|/101.5 ≈ 0.133
        alert = detector.update(make_agg(115.0, 9))
        assert alert is not None
        assert alert.kind == "SMA_deviation"
        assert alert.ticker == TICKER
        assert "above" in alert.message
        assert alert.extra["deviation_percent"] > 5.0
        assert alert.extra["simple_moving_average"] > 0.0

    def test_fires_falling(self):
        """Price well below the SMA triggers an alert (falling direction)."""
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 9)
        # Price drops ~15% below baseline → deviation ≈ 13.7% > 5%
        # mean = (9×100 + 85) / 10 = 98.5  →  |85−98.5|/98.5 ≈ 0.137
        alert = detector.update(make_agg(85.0, 9))
        assert alert is not None
        assert alert.kind == "SMA_deviation"
        assert alert.ticker == TICKER
        assert "below" in alert.message
        assert alert.extra["deviation_percent"] > 5.0
        assert alert.extra["simple_moving_average"] > 0.0
