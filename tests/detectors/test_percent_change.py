from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate, MarketInfo
from portfolio_monitor.detectors.percent_change import PercentChangeDetector
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

TICKER = AssetSymbol("AAPL", AssetTypes.Stock)
BASE_TIME = datetime(2025, 1, 2, 12, 0, tzinfo=ZoneInfo("UTC"))


def make_agg(ticker: AssetSymbol, close: float, minute: int, *, volume: float = 1000.0, base_time: datetime = BASE_TIME) -> Aggregate:
    return Aggregate(
        symbol=ticker,
        date_open=base_time + timedelta(minutes=minute),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        timespan=timedelta(minutes=1),
    )


# ---------------------------------------------------------------------------
# PercentChangeDetector
# ---------------------------------------------------------------------------


class TestPercentChangeDetector:
    def test_no_alert_first_candle(self):
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        assert not detector.is_primed(TICKER)
        detector.update(make_agg(TICKER, 100.0, 0))
        assert not detector.is_primed(TICKER)
        assert detector.get_current_alert(TICKER) is None

    def test_no_alert_below_threshold(self):
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(TICKER, 100.0, 0))
        # 1% change vs oldest reference — below threshold
        detector.update(make_agg(TICKER, 101.0, 5))
        assert detector.is_primed(TICKER)
        assert detector.get_current_alert(TICKER) is None

    def test_fires_rising(self):
        """Price rise above threshold vs period reference triggers alert (rising direction).

        With period="5m" and two candles 1 minute apart, the oldest entry
        (t=0, close=100) is within the window and used as the reference.
        Change = (104−100)/100 = 4% > 3% → fires.
        """
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(TICKER, 100.0, 0))
        detector.update(make_agg(TICKER, 104.0, 5))
        assert detector.is_primed(TICKER)

        alert = detector.get_current_alert(TICKER)
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
        detector.update(make_agg(TICKER, 100.0, 0))
        detector.update(make_agg(TICKER, 96.0, 5))
        assert detector.is_primed(TICKER)
        alert = detector.get_current_alert(TICKER)
        assert alert is not None
        assert alert.kind == "percent_change"
        assert alert.ticker == TICKER
        assert alert.extra["percent_change"] < 0.0
        assert alert.extra["percent_change"] < -3.0

    def test_update_preserves_id(self):
        """When condition persists in the same direction, alert id stays the same."""
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(TICKER, 100.0, 0))
        detector.update(make_agg(TICKER, 104.0, 5))
        assert detector.is_primed(TICKER)

        first_alert = detector.get_current_alert(TICKER)
        assert first_alert is not None
        first_id = first_alert.id
        first_change = first_alert.extra["percent_change"]

        # Condition continues at higher pct
    
        detector.update(make_agg(TICKER, 110.0, 10))
        updated_alert = detector.get_current_alert(TICKER)
        assert updated_alert is not None
        assert updated_alert.id == first_id
        assert updated_alert is not first_alert
        assert updated_alert.extra["percent_change"] > first_alert.extra["percent_change"]

    def test_update_preserves_id_day(self):
        """When condition persists in the same direction, alert id stays the same."""
        detector = PercentChangeDetector(threshold=0.03, period="1d")
        base_time = datetime(2025, 1, 2, 15, 59, tzinfo=ZoneInfo("America/New_York"))
        detector.update(make_agg(TICKER, 100.0, 0, base_time=base_time))
        detector.update(make_agg(TICKER, 104.0, 24*60, base_time=base_time))
        assert detector.is_primed(TICKER)

        first_alert = detector.get_current_alert(TICKER)
        assert first_alert is not None
        first_id = first_alert.id

        # Condition continues at higher pct
    
        detector.update(make_agg(TICKER, 110.0, 2*24*60, base_time=base_time))
        updated_alert = detector.get_current_alert(TICKER)
        assert updated_alert is not None
        assert updated_alert.id == first_id
        assert updated_alert is not first_alert
        assert updated_alert.extra["percent_change"] > first_alert.extra["percent_change"]

    
    def test_update_preserves_id_day_bad_data(self):
        """
        When condition persists in the same direction, alert id stays the same.
        This test simulates getting bad data from the API for previous close which
        returns an aggragate with the open time set to the market close time.
        """
        detector = PercentChangeDetector(threshold=0.03, period="1d")
        base_time = datetime(2025, 1, 2, 16, 00, tzinfo=ZoneInfo("America/New_York"))
        detector.update(make_agg(TICKER, 100.0, 0, base_time=base_time))
        detector.update(make_agg(TICKER, 104.0, 24*60, base_time=base_time))
        assert detector.is_primed(TICKER)

        first_alert = detector.get_current_alert(TICKER)
        assert first_alert is not None
        first_id = first_alert.id
        first_change = first_alert.extra["percent_change"]

        # Condition continues at higher pct
    
        detector.update(make_agg(TICKER, 110.0, 2*24*60, base_time=base_time))
        updated_alert = detector.get_current_alert(TICKER)
        assert updated_alert is not None
        assert updated_alert.id == first_id
        assert updated_alert is not first_alert
        assert updated_alert.extra["percent_change"] > first_alert.extra["percent_change"]

    

    def test_direction_change_creates_new_alert(self):
        """Switching direction clears old alert and starts a new one with a different id."""
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(TICKER, 100.0, 0))
        detector.update(make_agg(TICKER, 104.0, 5))
        first_alert = detector.get_current_alert(TICKER)
        assert first_alert is not None
        first_id = first_alert.id

        # Swing to negative direction
        detector.update(make_agg(TICKER, 96.0, 10))
        new_alert = detector.get_current_alert(TICKER)
        assert new_alert is not None
        assert new_alert.id != first_id
        assert new_alert.extra["percent_change"] < 0.0

    def test_clear_removes_alert(self):
        """clear() resets alert state."""
        detector = PercentChangeDetector(threshold=0.03, period="5m")
        detector.update(make_agg(TICKER, 100.0, 0))
        detector.update(make_agg(TICKER, 104.0, 5))
        assert detector.get_current_alert(TICKER) is not None

        detector.clear(TICKER)
        assert detector.get_current_alert(TICKER) is None
