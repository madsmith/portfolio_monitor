from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.moving_average_deviation import SMADeviationDetector
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

TICKER = AssetSymbol("AAPL", AssetTypes.Stock)
BASE_TIME = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))


def make_agg(symbol: AssetSymbol, close: float, minute: int, *, volume: float = 1000.0) -> Aggregate:
    return Aggregate(
        symbol=symbol,
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
        detector.update(make_agg(TICKER, price, i))
    assert detector.is_primed(TICKER)


class TestSMADeviationDetector:
    def test_no_alert_below_threshold(self):
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 30)
        # 1% rise — well below the 5% threshold
        detector.update(make_agg(TICKER, 101.0, 30))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_insufficient_data(self):
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        # Single candle: price == mean, deviation = 0
        detector.update(make_agg(TICKER, 100.0, 0))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_rising(self):
        """Price well above the SMA triggers an alert (rising direction)."""
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 30)
        # Price jumps ~15% above baseline → deviation ≈ 13.3% > 5%
        # mean = (30×100 + 115) / 31 = 100.48  →  |115−100.48|/100.48 ≈ 0.144
        detector.update(make_agg(TICKER, 115.0, 30))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "SMA_deviation"
        assert alert.ticker == TICKER
        assert "above" in alert.message
        assert alert.extra["deviation_percent"] > 5.0
        assert alert.extra["simple_moving_average"] > 0.0

    def test_fires_falling(self):
        """Price well below the SMA triggers an alert (falling direction)."""
        detector = SMADeviationDetector(period="30m", threshold=0.05)
        feed_stable(detector, 30)
        # Price drops ~15% below baseline → deviation ≈ 13.7% > 5%
        # mean = (30×100 + 85) / 31 = 100.48  →  |85−100.48|/100.48 ≈ 0.154
        detector.update(make_agg(TICKER, 85.0, 30))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "SMA_deviation"
        assert alert.ticker == TICKER
        assert "below" in alert.message
        assert alert.extra["deviation_percent"] > 5.0
        assert alert.extra["simple_moving_average"] > 0.0
