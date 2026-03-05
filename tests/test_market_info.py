"""Comprehensive tests for MarketInfo — all public APIs, time boundaries, crypto vs stock."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from portfolio_monitor.data.market_info import MarketInfo, MarketStatus
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_UTC = ZoneInfo("UTC")
_ET = ZoneInfo("America/New_York")

BTC = AssetSymbol("BTC", AssetTypes.Crypto)
AAPL = AssetSymbol("AAPL", AssetTypes.Stock)

# June 2025 reference dates (EDT = UTC-4):
# 2025-06-06 = Friday
# 2025-06-07 = Saturday
# 2025-06-08 = Sunday
# 2025-06-09 = Monday
# 2025-06-10 = Tuesday
# 2025-06-11 = Wednesday


def et(y: int, m: int, d: int, h: int = 0, mn: int = 0, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mn, s, tzinfo=_ET)


def utc(y: int, m: int, d: int, h: int = 0, mn: int = 0, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mn, s, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# get_market_status
# ---------------------------------------------------------------------------


class TestGetMarketStatusCrypto:
    def test_weekday_midday(self) -> None:
        assert MarketInfo.get_market_status(BTC, utc(2025, 6, 10, 12)) == MarketStatus.OPEN

    def test_saturday_is_open(self) -> None:
        assert MarketInfo.get_market_status(BTC, utc(2025, 6, 7, 12)) == MarketStatus.OPEN

    def test_midnight_utc_is_open(self) -> None:
        assert MarketInfo.get_market_status(BTC, utc(2025, 6, 10, 0, 0, 0)) == MarketStatus.OPEN


class TestGetMarketStatusStock:
    """All four status zones and their exact entry/exit boundaries (Eastern time)."""

    # ── CLOSE: before pre-market ──────────────────────────────────────────────

    def test_just_before_pre_market_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 3, 59, 59)) == MarketStatus.CLOSE

    def test_midnight_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 0, 0, 0)) == MarketStatus.CLOSE

    # ── PRE_TRADING: 04:00 – 09:29:59 ET ────────────────────────────────────

    def test_at_pre_market_open_is_pre_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 4, 0, 0)) == MarketStatus.PRE_TRADING

    def test_mid_pre_market_is_pre_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 7, 0, 0)) == MarketStatus.PRE_TRADING

    def test_just_before_open_is_pre_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 9, 29, 59)) == MarketStatus.PRE_TRADING

    # ── OPEN: 09:30 – 15:59:59 ET ───────────────────────────────────────────

    def test_at_market_open_is_open(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 9, 30, 0)) == MarketStatus.OPEN

    def test_mid_session_is_open(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 12, 0, 0)) == MarketStatus.OPEN

    def test_just_before_close_is_open(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 15, 59, 59)) == MarketStatus.OPEN

    # ── AFTER_TRADING: 16:00 – 19:59:59 ET ──────────────────────────────────

    def test_at_market_close_is_after_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 16, 0, 0)) == MarketStatus.AFTER_TRADING

    def test_mid_after_hours_is_after_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 18, 0, 0)) == MarketStatus.AFTER_TRADING

    def test_just_before_after_close_is_after_trading(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 19, 59, 59)) == MarketStatus.AFTER_TRADING

    # ── CLOSE: 20:00+ ET ─────────────────────────────────────────────────────

    def test_at_after_close_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 20, 0, 0)) == MarketStatus.CLOSE

    def test_late_evening_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 10, 23, 0, 0)) == MarketStatus.CLOSE

    # ── Weekend ──────────────────────────────────────────────────────────────

    def test_saturday_midday_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 7, 12, 0, 0)) == MarketStatus.CLOSE

    def test_sunday_midday_is_close(self) -> None:
        assert MarketInfo.get_market_status(AAPL, et(2025, 6, 8, 12, 0, 0)) == MarketStatus.CLOSE


# ---------------------------------------------------------------------------
# is_market_open
# ---------------------------------------------------------------------------


class TestIsMarketOpen:
    def test_crypto_always_open(self) -> None:
        assert MarketInfo.is_market_open(BTC, et(2025, 6, 7, 12)) is True

    def test_stock_open_during_session(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 10, 12)) is True

    def test_stock_open_during_pre_trading(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 10, 5)) is True

    def test_stock_open_during_after_trading(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 10, 17)) is True

    def test_stock_not_open_before_pre_market(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 10, 3)) is False

    def test_stock_not_open_after_after_hours(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 10, 21)) is False

    def test_stock_not_open_on_weekend(self) -> None:
        assert MarketInfo.is_market_open(AAPL, et(2025, 6, 7, 12)) is False


# ---------------------------------------------------------------------------
# is_market_closed
# ---------------------------------------------------------------------------


class TestIsMarketClosed:
    def test_crypto_never_closed(self) -> None:
        assert MarketInfo.is_market_closed(BTC, et(2025, 6, 7, 12)) is False

    def test_stock_closed_before_pre_market(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 10, 3)) is True

    def test_stock_closed_after_after_hours(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 10, 21)) is True

    def test_stock_closed_on_saturday(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 7, 12)) is True

    def test_stock_closed_on_sunday(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 8, 12)) is True

    def test_stock_not_closed_during_session(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 10, 12)) is False

    def test_stock_not_closed_during_pre_trading(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 10, 5)) is False

    def test_stock_not_closed_during_after_trading(self) -> None:
        assert MarketInfo.is_market_closed(AAPL, et(2025, 6, 10, 17)) is False


# ---------------------------------------------------------------------------
# is_market_pre_trading
# ---------------------------------------------------------------------------


class TestIsMarketPreTrading:
    def test_crypto_never_pre_trading(self) -> None:
        assert MarketInfo.is_market_pre_trading(BTC, et(2025, 6, 10, 5)) is False

    def test_stock_true_during_pre_trading(self) -> None:
        assert MarketInfo.is_market_pre_trading(AAPL, et(2025, 6, 10, 6)) is True

    def test_stock_false_during_session(self) -> None:
        assert MarketInfo.is_market_pre_trading(AAPL, et(2025, 6, 10, 12)) is False

    def test_stock_false_during_after_trading(self) -> None:
        assert MarketInfo.is_market_pre_trading(AAPL, et(2025, 6, 10, 17)) is False

    def test_stock_false_before_pre_market(self) -> None:
        assert MarketInfo.is_market_pre_trading(AAPL, et(2025, 6, 10, 2)) is False

    def test_stock_false_on_weekend(self) -> None:
        assert MarketInfo.is_market_pre_trading(AAPL, et(2025, 6, 7, 6)) is False


# ---------------------------------------------------------------------------
# is_market_after_trading
# ---------------------------------------------------------------------------


class TestIsMarketAfterTrading:
    def test_crypto_never_after_trading(self) -> None:
        assert MarketInfo.is_market_after_trading(BTC, et(2025, 6, 10, 17)) is False

    def test_stock_true_during_after_trading(self) -> None:
        assert MarketInfo.is_market_after_trading(AAPL, et(2025, 6, 10, 17)) is True

    def test_stock_false_during_session(self) -> None:
        assert MarketInfo.is_market_after_trading(AAPL, et(2025, 6, 10, 12)) is False

    def test_stock_false_during_pre_trading(self) -> None:
        assert MarketInfo.is_market_after_trading(AAPL, et(2025, 6, 10, 6)) is False

    def test_stock_false_after_after_close(self) -> None:
        assert MarketInfo.is_market_after_trading(AAPL, et(2025, 6, 10, 21)) is False

    def test_stock_false_on_weekend(self) -> None:
        assert MarketInfo.is_market_after_trading(AAPL, et(2025, 6, 7, 17)) is False


# ---------------------------------------------------------------------------
# get_market_close
# ---------------------------------------------------------------------------


class TestGetMarketCloseCrypto:
    """Crypto close = 23:59:59.999 UTC on the same calendar date (in UTC) as input."""

    def test_weekday_noon_utc(self) -> None:
        close = MarketInfo.get_market_close(BTC, utc(2025, 6, 10, 12))
        assert close == utc(2025, 6, 10, 23, 59, 59) + timedelta(milliseconds=999)

    def test_midnight_utc(self) -> None:
        close = MarketInfo.get_market_close(BTC, utc(2025, 6, 10, 0, 0, 0))
        assert close == utc(2025, 6, 10, 23, 59, 59) + timedelta(milliseconds=999)

    def test_just_before_midnight_utc(self) -> None:
        close = MarketInfo.get_market_close(BTC, utc(2025, 6, 10, 23, 59, 58))
        assert close == utc(2025, 6, 10, 23, 59, 59) + timedelta(milliseconds=999)

    def test_eastern_evening_crosses_utc_date(self) -> None:
        # 23:00 EDT (UTC-4) = 03:00 UTC next day → close falls on the next UTC date
        close = MarketInfo.get_market_close(BTC, et(2025, 6, 10, 23, 0, 0))
        assert close == utc(2025, 6, 11, 23, 59, 59) + timedelta(milliseconds=999)

    def test_close_precision_is_999ms(self) -> None:
        close = MarketInfo.get_market_close(BTC, utc(2025, 6, 10, 12))
        assert close.microsecond == 999_000

    def test_weekend_same_as_weekday(self) -> None:
        close = MarketInfo.get_market_close(BTC, utc(2025, 6, 7, 12))
        assert close == utc(2025, 6, 7, 23, 59, 59) + timedelta(milliseconds=999)


class TestGetMarketCloseStock:
    """Stock close = 16:00 ET on the nearest preceding-or-same trading day."""

    def test_tuesday_midday_returns_tuesday_close(self) -> None:
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 10, 12))
        assert close == et(2025, 6, 10, 16, 0, 0)

    def test_friday_returns_friday_close(self) -> None:
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 6, 12))
        assert close == et(2025, 6, 6, 16, 0, 0)

    def test_saturday_steps_back_to_friday(self) -> None:
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 7, 12))
        assert close == et(2025, 6, 6, 16, 0, 0)

    def test_sunday_steps_back_to_friday(self) -> None:
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 8, 12))
        assert close == et(2025, 6, 6, 16, 0, 0)

    def test_late_friday_et_crosses_saturday_utc_still_friday_close(self) -> None:
        # Friday 23:00 EDT = Saturday 03:00 UTC — UTC date is Saturday, but result is still Friday close
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 6, 23, 0, 0))
        assert close == et(2025, 6, 6, 16, 0, 0)

    def test_result_timezone_is_eastern(self) -> None:
        close = MarketInfo.get_market_close(AAPL, et(2025, 6, 10, 12))
        close_et = close.astimezone(_ET)
        assert close_et.hour == 16
        assert close_et.minute == 0


# ---------------------------------------------------------------------------
# get_market_day_timespan
# ---------------------------------------------------------------------------


class TestGetMarketDayTimespan:
    def test_crypto_is_24_hours(self) -> None:
        assert MarketInfo.get_market_day_timespan(BTC) == timedelta(hours=24)

    def test_stock_is_16_hours(self) -> None:
        # pre-market 04:00 → after-close 20:00 = 16 hours
        assert MarketInfo.get_market_day_timespan(AAPL) == timedelta(hours=16)


# ---------------------------------------------------------------------------
# get_previous_market_close
# ---------------------------------------------------------------------------


class TestGetPreviousMarketCloseCrypto:
    """Crypto: previous close = 23:59:59.999 UTC of the preceding UTC calendar day."""

    def test_midday_returns_previous_day(self) -> None:
        prev = MarketInfo.get_previous_market_close(BTC, utc(2025, 6, 10, 12))
        assert prev == utc(2025, 6, 9, 23, 59, 59) + timedelta(milliseconds=999)

    def test_just_past_midnight_returns_previous_day(self) -> None:
        prev = MarketInfo.get_previous_market_close(BTC, utc(2025, 6, 10, 0, 0, 1))
        assert prev == utc(2025, 6, 9, 23, 59, 59) + timedelta(milliseconds=999)

    def test_crosses_month_boundary(self) -> None:
        prev = MarketInfo.get_previous_market_close(BTC, utc(2025, 6, 1, 12))
        assert prev == utc(2025, 5, 31, 23, 59, 59) + timedelta(milliseconds=999)

    def test_weekend_input_returns_previous_day(self) -> None:
        prev = MarketInfo.get_previous_market_close(BTC, utc(2025, 6, 7, 12))  # Saturday
        assert prev == utc(2025, 6, 6, 23, 59, 59) + timedelta(milliseconds=999)

    def test_close_precision_is_999ms(self) -> None:
        prev = MarketInfo.get_previous_market_close(BTC, utc(2025, 6, 10, 12))
        assert prev.microsecond == 999_000


class TestGetPreviousMarketCloseStock:
    """
    Session boundary: before 04:00 ET the previous calendar-day session is still
    active, so the reference close looks one session further back.

    Key cases:
      - Weekday >= 04:00 ET  → previous business day close
      - Monday (any time)    → Friday close (skips weekend regardless of 04:00 rule)
      - Weekday < 04:00 ET   → two business days back (before 4AM is "still Monday")
    """

    def test_tuesday_midday_returns_monday_close(self) -> None:
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 10, 10))
        assert prev == et(2025, 6, 9, 16)

    def test_wednesday_midday_returns_tuesday_close(self) -> None:
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 11, 10))
        assert prev == et(2025, 6, 10, 16)

    def test_monday_midday_skips_weekend_returns_friday(self) -> None:
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 9, 10))
        assert prev == et(2025, 6, 6, 16)

    def test_monday_early_morning_still_returns_friday(self) -> None:
        # Before 04:00 on Monday: session_date=Sunday, candidate=Saturday→Friday
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 9, 3))
        assert prev == et(2025, 6, 6, 16)

    def test_tuesday_at_pre_market_boundary_returns_monday(self) -> None:
        # Exactly 04:00 ET on Tuesday: session_date=Tuesday, candidate=Monday
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 10, 4, 0, 0))
        assert prev == et(2025, 6, 9, 16)

    def test_tuesday_just_before_pre_market_returns_friday(self) -> None:
        # 03:59 ET on Tuesday: session_date=Monday, candidate skips weekend → Friday
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 10, 3, 59, 59))
        assert prev == et(2025, 6, 6, 16)

    def test_wednesday_before_pre_market_returns_monday(self) -> None:
        # 03:00 ET on Wednesday: session_date=Tuesday, candidate=Monday
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 11, 3))
        assert prev == et(2025, 6, 9, 16)

    def test_utc_input_converts_correctly(self) -> None:
        # 14:00 UTC = 10:00 EDT (UTC-4) on Tuesday → previous close is Monday
        prev = MarketInfo.get_previous_market_close(AAPL, utc(2025, 6, 10, 14))
        assert prev == et(2025, 6, 9, 16)

    def test_result_timezone_is_eastern(self) -> None:
        prev = MarketInfo.get_previous_market_close(AAPL, et(2025, 6, 10, 10))
        prev_et = prev.astimezone(_ET)
        assert prev_et.hour == 16
        assert prev_et.minute == 0
