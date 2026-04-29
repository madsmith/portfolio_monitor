import dataclasses
import inspect
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, NamedTuple, Protocol, Type, TypeVar, runtime_checkable
from uuid import uuid4

from portfolio_monitor.core import parse_period
from portfolio_monitor.data import Aggregate
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    id: str
    detector_id: str  # Unique ID of the detector instance that created this alert
    ticker: AssetSymbol
    kind: str
    message: str
    extra: dict[str, Any]
    at: datetime
    updated_at: datetime
    aggregate: Aggregate  # The price aggregate that triggered the alert

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "detector_id": self.detector_id,
            "ticker": self.ticker.to_dict(),
            "kind": self.kind,
            "message": self.message,
            "extra": _round_floats(self.extra),
            "at": self.at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "aggregate": self.aggregate.to_dict(),
        }


@dataclass
class DetectorArgSpec:
    """Describes one constructor argument for a Detector class."""

    name: str
    type: str   # human-readable, e.g. "float", "str", "int"
    default: Any  # inspect.Parameter.empty when the arg is required

    @property
    def required(self) -> bool:
        return self.default is inspect.Parameter.empty


@dataclass
class DetectorInfo:
    """Describes a detector class: its name and constructor arguments."""

    name: str
    args: list[DetectorArgSpec]


def _round_floats(obj: Any, precision: int = 4) -> Any:
    if isinstance(obj, float):
        return round(obj, precision)
    if isinstance(obj, dict):
        return {k: _round_floats(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, precision) for v in obj]
    return obj


@runtime_checkable
class Detector(Protocol):
    @property
    def detector_id(self) -> str:
        """Return the unique ID for this detector instance."""
        ...

    @classmethod
    def name(cls) -> str:
        """Return the detector's name (used for alert kind)."""
        ...

    @classmethod
    def detector_info(cls) -> DetectorInfo:
        """Return the name and constructor arg spec for this detector class."""
        ...

    def update(self, aggregate: Aggregate) -> None:
        """Update the detector with the latest aggregate, updating internal alert state."""
        ...

    def get_current_alert(self, symbol: AssetSymbol) -> Alert | None:
        """Return the currently active alert for a symbol, or None."""
        ...

    def clear(self, symbol: AssetSymbol) -> None:
        """Clear the active alert state for a symbol, allowing a fresh alert to fire."""
        ...

    def is_primed(self, symbol: AssetSymbol) -> bool:
        """Return True if the detector has enough historical data to detect properly."""
        ...

    def prime_age(self) -> timedelta | int:
        """Return how far back from current_time data is needed to prime this detector."""
        ...

    def reset(self) -> None:
        """Clear all per-symbol alert state. Does not clear accumulated history."""
        ...


class DetectorBase(ABC, Detector):
    def __init__(self) -> None:
        self._detector_id: str = uuid4().hex
        self._current_alerts: dict[AssetSymbol, Alert | None] = {}

    @property
    def detector_id(self) -> str:
        return self._detector_id

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        raise NotImplementedError

    @classmethod
    def detector_info(cls) -> DetectorInfo:
        signature = inspect.signature(cls.__init__)
        args = []
        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue
            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                type_str = "any"
            elif hasattr(annotation, "__name__"):
                type_str = annotation.__name__
            else:
                type_str = str(annotation)
            args.append(DetectorArgSpec(name=param_name, type=type_str, default=param.default))
        return DetectorInfo(name=cls.name(), args=args)

    @abstractmethod
    def update(self, aggregate: Aggregate) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_primed(self, symbol: AssetSymbol) -> bool:
        """Return True when the detector has accumulated enough history to produce
        meaningful alerts for this symbol. Must return False while prime() is
        actively replaying historical data."""
        raise NotImplementedError

    @abstractmethod
    def prime_age(self) -> timedelta | int:
        """Return how far back from current_time data is needed to prime this detector."""
        raise NotImplementedError

    def get_current_alert(self, symbol: AssetSymbol) -> Alert | None:
        return self._current_alerts.get(symbol)

    def clear(self, symbol: AssetSymbol) -> None:
        self._current_alerts.pop(symbol, None)

    def reset(self) -> None:
        self._current_alerts.clear()

    # ------------------------------------------------------------------
    # Protected helpers for subclasses
    # ------------------------------------------------------------------

    def _start_alert(
        self, symbol: AssetSymbol, message: str, extra: dict[str, Any], aggregate: Aggregate
    ) -> None:
        """Begin a new alert occurrence. No-op until is_primed() returns True."""
        if not self.is_primed(symbol):
            return
        now = datetime.now(aggregate.date_open.tzinfo)
        self._current_alerts[symbol] = Alert(
            id=uuid4().hex,
            detector_id=self._detector_id,
            ticker=symbol,
            kind=self.name(),
            message=message,
            extra=extra,
            at=now,
            updated_at=now,
            aggregate=aggregate,
        )

    def _update_current_alert(
        self, symbol: AssetSymbol, message: str, extra: dict[str, Any], aggregate: Aggregate
    ) -> None:
        """Update an existing alert's data, preserving id and at. No-op until is_primed()."""
        if not self.is_primed(symbol):
            return
        existing = self._current_alerts.get(symbol)
        if existing is None:
            # No existing alert — start a new one instead
            self._start_alert(symbol, message, extra, aggregate)
            return
        now = datetime.now(aggregate.date_open.tzinfo)
        self._current_alerts[symbol] = dataclasses.replace(
            existing,
            message=message,
            extra=extra,
            updated_at=now,
            aggregate=aggregate,
        )

    def _clear_alert(self, symbol: AssetSymbol) -> None:
        """Clear the active alert for this symbol."""
        self._current_alerts.pop(symbol, None)

    def _fire_or_update_alert(
        self, symbol: AssetSymbol, message: str, extra: dict[str, Any], aggregate: Aggregate
    ) -> None:
        """Start a new alert or update the existing one — whichever is appropriate."""
        if self.get_current_alert(symbol) is None:
            self._start_alert(symbol, message, extra, aggregate)
        else:
            self._update_current_alert(symbol, message, extra, aggregate)


T = TypeVar("T")


class HistoryRecord(Generic[T], NamedTuple):
    timestamp: datetime
    value: T


class TimeRangeDetectorBase(DetectorBase, Generic[T]):
    def __init__(self, period: str = "2h") -> None:
        super().__init__()
        self.period = period
        self.period_delta = parse_period(period)
        self.histories: dict[AssetSymbol, list[HistoryRecord[T]]] = defaultdict(list)

    def update(self, aggregate: Aggregate) -> None:
        self._append_history(aggregate)
        self._history_cleanup(aggregate.symbol, aggregate.date_open + aggregate.timespan)
        self._compute_alert_state(aggregate)

    @abstractmethod
    def _value_from_aggregate(self, aggregate: Aggregate) -> T:
        raise NotImplementedError

    @abstractmethod
    def _compute_alert_state(self, aggregate: Aggregate) -> None:
        """Compute and update alert state using _start_alert / _update_current_alert / _clear_alert."""
        raise NotImplementedError

    def values(self, symbol: AssetSymbol) -> list[T]:
        return [record.value for record in self.histories[symbol]]

    def _append_history(self, aggregate: Aggregate) -> None:
        timestamp = aggregate.date_open + aggregate.timespan
        value = self._value_from_aggregate(aggregate)
        new_record = HistoryRecord[T](timestamp, value)
        self.histories[aggregate.symbol].append(new_record)

    def _history_cleanup(self, symbol: AssetSymbol, current_time: datetime) -> None:
        cutoff_time = current_time - self.period_delta
        self.histories[symbol] = [
            record
            for record in self.histories[symbol]
            if record.timestamp >= cutoff_time
        ]

    def is_primed(self, symbol: AssetSymbol) -> bool:
        if not self.histories.get(symbol):
            return False
        
        # Check if we have a datapoint old enough to cover the full period.
        # Since we crop the history on update, we will assum we have enough data
        # if the date of the olderst record is without 5% of the opening of the period.
        oldest = self.histories[symbol][0]
        current = self.histories[symbol][-1]

        period_start = current.timestamp - self.period_delta
        primed_threshold = period_start + self.period_delta * 0.05
        return oldest.timestamp <= primed_threshold

    def prime_age(self) -> timedelta | int:
        return self.period_delta


class SampleRangeDetectorBase(DetectorBase):
    def __init__(self, samples: int = 60) -> None:
        super().__init__()
        self.samples = samples

