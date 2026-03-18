from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from portfolio_monitor.core.datetime import parse_period_parts


class Timespan(str, Enum):
    SECOND  = "second"
    MINUTE  = "minute"
    HOUR    = "hour"
    DAY     = "day"
    WEEK    = "week"
    MONTH   = "month"
    QUARTER = "quarter"
    YEAR    = "year"

    def __str__(self) -> str:
        return self.value


_SHORTHAND: dict[str, Timespan] = {
    "s":  Timespan.SECOND,
    "m":  Timespan.MINUTE,
    "h":  Timespan.HOUR,
    "d":  Timespan.DAY,
    "w":  Timespan.WEEK,
    "mo": Timespan.MONTH,
    "y":  Timespan.YEAR,
}

_SHORTHAND_REV: dict[Timespan, str] = {v: k for k, v in _SHORTHAND.items()}

_DEFAULT_MULTIPLIER = 1
_DEFAULT_TIMESPAN = Timespan.MINUTE

# Approximate seconds per unit — used only for limit estimation, not for accuracy
_APPROX_SECONDS: dict[Timespan, int] = {
    Timespan.SECOND:  1,
    Timespan.MINUTE:  60,
    Timespan.HOUR:    3_600,
    Timespan.DAY:     86_400,
    Timespan.WEEK:    604_800,
    Timespan.MONTH:   2_592_000,
    Timespan.QUARTER: 7_776_000,
    Timespan.YEAR:    31_536_000,
}


@dataclass(frozen=True)
class AggregateTimespan:
    multiplier: int
    timespan: Timespan

    def __post_init__(self) -> None:
        if self.multiplier < 1:
            raise ValueError(f"multiplier must be >= 1, got {self.multiplier!r}")

    @classmethod
    def default(cls) -> AggregateTimespan:
        """The standard 1-minute aggregate used for real-time caching."""
        return cls(multiplier=_DEFAULT_MULTIPLIER, timespan=_DEFAULT_TIMESPAN)

    @classmethod
    def parse(cls, value: str) -> AggregateTimespan:
        """Parse a shorthand string like '1m', '5m', '15m', '1H', '4h', '1d'.

        Supported suffixes: s, m, h, d, w, mo, y (case-insensitive).
        Raises ValueError for unrecognised formats.
        """
        multiplier, unit = parse_period_parts(value)
        timespan = _SHORTHAND.get(unit)
        if timespan is None:
            raise ValueError(
                f"invalid timespan {value!r}; "
                "expected format like '1m', '5m', '1h', '1d'"
            )
        return cls(multiplier=multiplier, timespan=timespan)

    def is_cacheable(self) -> bool:
        """Only default 1-minute aggregates are stored in the cache."""
        return self.multiplier == _DEFAULT_MULTIPLIER and self.timespan == _DEFAULT_TIMESPAN

    def approx_candle_count(self, seconds: float) -> int:
        """Estimate the number of candles that fit in *seconds* of wall time."""
        candle_secs = self.multiplier * _APPROX_SECONDS.get(self.timespan, 60)
        return max(1, int(seconds / candle_secs)) + 2

    def __str__(self) -> str:
        return f"{self.multiplier}{_SHORTHAND_REV[self.timespan]}"
