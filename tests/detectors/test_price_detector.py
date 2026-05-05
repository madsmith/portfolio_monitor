from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors.price_value import PriceValueDetector
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

TICKER = AssetSymbol("AAPL", AssetTypes.Stock)
BASE_TIME = datetime(2025, 1, 2, 12, 0, tzinfo=ZoneInfo("UTC"))


def make_agg(symbol: AssetSymbol, close: float, minute: int = 0) -> Aggregate:
    return Aggregate(
        symbol=symbol,
        date_open=BASE_TIME + timedelta(minutes=minute),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        timespan=timedelta(minutes=1),
    )


class TestPriceValueDetector:
    def test_is_primed_immediately(self):
        """PriceValueDetector requires no warmup — primed before any update."""
        detector = PriceValueDetector(limit=100.0)
        assert detector.is_primed(TICKER)

    def test_no_alert_below_limit_direction_above(self):
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 99.99))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_at_limit_direction_above(self):
        """Condition is strictly greater than — price equal to limit does not fire."""
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 100.0))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_above(self):
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 100.01))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "price_value"
        assert alert.ticker == TICKER
        assert alert.extra["limit"] == 100.0
        assert alert.extra["direction"] == "above"

    def test_no_alert_above_limit_direction_below(self):
        detector = PriceValueDetector(limit=100.0, direction="below")
        detector.update(make_agg(TICKER, 100.01))
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_at_limit_direction_below(self):
        """Condition is strictly less than — price equal to limit does not fire."""
        detector = PriceValueDetector(limit=100.0, direction="below")
        detector.update(make_agg(TICKER, 100.0))
        assert detector.get_current_alert(TICKER) is None

    def test_fires_below(self):
        detector = PriceValueDetector(limit=100.0, direction="below")
        detector.update(make_agg(TICKER, 99.99))
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "price_value"
        assert alert.ticker == TICKER
        assert alert.extra["limit"] == 100.0
        assert alert.extra["direction"] == "below"

    def test_default_direction_is_above(self):
        """Omitting direction defaults to 'above'."""
        detector = PriceValueDetector(limit=50.0)
        detector.update(make_agg(TICKER, 50.01))
        assert detector.get_current_alert(TICKER) is not None
        detector2 = PriceValueDetector(limit=50.0)
        detector2.update(make_agg(TICKER, 49.99))
        assert detector2.get_current_alert(TICKER) is None

    def test_update_preserves_id(self):
        """Sustained trigger updates the alert in place rather than creating a new one."""
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 101.0, minute=0))
        first_alert = detector.get_current_alert(TICKER)
        assert first_alert is not None
        first_id = first_alert.id

        detector.update(make_agg(TICKER, 102.0, minute=1))
        updated_alert = detector.get_current_alert(TICKER)
        assert updated_alert is not None
        assert updated_alert.id == first_id
        assert updated_alert is not first_alert

    def test_clears_when_price_returns_to_safe_zone(self):
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 101.0, minute=0))
        assert detector.get_current_alert(TICKER) is not None

        detector.update(make_agg(TICKER, 99.0, minute=1))
        assert detector.get_current_alert(TICKER) is None

    def test_clears_below_direction(self):
        detector = PriceValueDetector(limit=100.0, direction="below")
        detector.update(make_agg(TICKER, 99.0, minute=0))
        assert detector.get_current_alert(TICKER) is not None

        detector.update(make_agg(TICKER, 101.0, minute=1))
        assert detector.get_current_alert(TICKER) is None

    def test_clear_method_resets_state(self):
        detector = PriceValueDetector(limit=100.0, direction="above")
        detector.update(make_agg(TICKER, 101.0))
        assert detector.get_current_alert(TICKER) is not None

        detector.clear(TICKER)
        assert detector.get_current_alert(TICKER) is None
