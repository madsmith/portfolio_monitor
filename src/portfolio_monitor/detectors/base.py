import dataclasses
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, NamedTuple, Protocol, Type, TypeVar, runtime_checkable
from uuid import uuid4

from portfolio_monitor.core.datetime import parse_period
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    id: str
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
            "ticker": self.ticker.to_dict(),
            "kind": self.kind,
            "message": self.message,
            "extra": _round_floats(self.extra),
            "at": self.at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "aggregate": self.aggregate.to_dict(),
        }


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
    def name(self) -> str:
        """Return the detector's name (used for alert kind)"""
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
        self._current_alerts: dict[AssetSymbol, Alert | None] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

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
            ticker=symbol,
            kind=self.name,
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
D = TypeVar("D", bound=Detector)


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


class DetectorRegistry:
    """Registry for detector classes that allows creating detectors from kind and config"""

    _registry: dict[str, Type[Detector]] = {}

    @classmethod
    def register(cls, detector_class: Type[D]) -> Type[D]:
        """Register a detector class by its name

        Can be used as a decorator:
        @DetectorRegistry.register
        class MyDetector(Detector):
            ...
        """
        # Create a temporary instance to get the name
        temp_instance = detector_class()
        name = temp_instance.name
        cls._registry[name] = detector_class
        return detector_class

    @classmethod
    def get_detector_class(cls, kind: str) -> Type[Detector] | None:
        """Get detector class by kind"""
        return cls._registry.get(kind)

    @classmethod
    def create_detector(
        cls, kind: str, config: dict[str, Any] | None = None
    ) -> Detector | None:
        """Create a detector instance from kind and config

        Args:
            kind: The detector kind/name to create
            config: Configuration parameters to pass to the detector constructor

        Returns:
            A configured detector instance or None if kind not found
        """
        if config is None:
            config = {}

        detector_class = cls.get_detector_class(kind)
        if detector_class is None:
            logger.warning(f"Detector kind {kind} not found")
            return None

        try:
            return detector_class(**config)
        except Exception as e:
            # Log the error and return None
            logger.error(f"Error creating detector {kind} with config {config}: {e}")
            return None

    @classmethod
    def list_available_detectors(cls) -> list[str]:
        """List all registered detector kinds"""
        return list(cls._registry.keys())
