import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.detectors.base import Alert, Detector
from portfolio_monitor.detectors.registry import DetectorRegistry
from portfolio_monitor.service.types import AssetSymbol

DetectorSpec = Detector | dict[str, Any]

logger = logging.getLogger(__name__)

# Set to True to prime detectors sequentially (useful for debugging)
PRIME_SEQUENTIALLY: bool = True


@dataclass
class AlertChange:
    """Describes a change in alert state produced by a single detect() call."""

    kind: Literal["fired", "updated", "cleared"]
    alert: Alert


class DeviationEngine:
    """
    Engine that manages multiple detectors and processes aggregates through them
    to generate stateful alert changes.
    """

    def __init__(
        self,
        default_detectors: Sequence[DetectorSpec] | None = None,
    ):
        self.default_detectors: list[Detector] = []
        if default_detectors:
            for detector in default_detectors:
                if isinstance(detector, Detector):
                    logger.debug("Adding default detector %s", detector.name())
                    self.default_detectors.append(detector)
                elif isinstance(detector, dict):
                    d = DetectorRegistry.create_detector(
                        detector["name"], detector.get("args")
                    )
                    if d is not None:
                        logger.debug("Adding default detector %s", d.name())
                        self.default_detectors.append(d)
                    else:
                        raise ValueError(f"Invalid detector: {detector}")
                else:
                    raise ValueError(f"Type {type(detector)} is not a valid detector")

        self.disabled_detectors: set[str] = set()
        self.asset_detectors: dict[AssetSymbol, list[Detector]] = {}

        # Tracks the last known active alert per (symbol, detector_id)
        self.active_alerts: dict[tuple[AssetSymbol, str], Alert] = {}

    def add_detector(self, symbol: AssetSymbol, detector: DetectorSpec) -> None:
        """Add a detector for a specific asset symbol."""
        if symbol not in self.asset_detectors:
            self.asset_detectors[symbol] = []

        if isinstance(detector, Detector):
            self.asset_detectors[symbol].append(detector)
        elif isinstance(detector, dict):
            d = DetectorRegistry.create_detector(detector["name"], detector.get("args"))
            if d is not None:
                logger.debug("Adding detector %s for symbol %s", d.name(), symbol)
                self.asset_detectors[symbol].append(d)
            else:
                raise ValueError(f"Invalid detector: {detector}")
        else:
            raise ValueError(f"Type {type(detector)} is not a valid detector")

    def get_available_detector_kinds(self) -> list[str]:
        return DetectorRegistry.list_available_detectors()

    def detect(self, aggregate: Aggregate) -> list[AlertChange]:
        """
        Process an aggregate through all applicable detectors.

        Returns a list of AlertChange describing transitions:
          - "fired"   — new alert started
          - "updated" — existing alert refreshed with new data
          - "cleared" — alert condition ended
        """
        changes: list[AlertChange] = []
        symbol = aggregate.symbol

        for detector in self._detectors_for_symbol(aggregate.symbol):
            if detector.name() in self.disabled_detectors:
                continue

            detector.update(aggregate)
            new_alert = detector.get_current_alert(symbol)
            key = (symbol, detector.detector_id)
            old_alert = self.active_alerts.get(key)

            if old_alert is None and new_alert is not None:
                self.active_alerts[key] = new_alert
                changes.append(AlertChange("fired", new_alert))

            elif old_alert is not None and new_alert is None:
                del self.active_alerts[key]
                changes.append(AlertChange("cleared", old_alert))

            elif old_alert is not None and new_alert is not None:
                if old_alert.id != new_alert.id:
                    # Direction/type changed — old cleared, new fired
                    del self.active_alerts[key]
                    changes.append(AlertChange("cleared", old_alert))
                    self.active_alerts[key] = new_alert
                    changes.append(AlertChange("fired", new_alert))
                else:
                    # Same occurrence, updated data
                    self.active_alerts[key] = new_alert
                    changes.append(AlertChange("updated", new_alert))

        return changes

    def get_active_alerts(self) -> list[Alert]:
        """Return all currently active alerts."""
        return list(self.active_alerts.values())

    def reset_state(self) -> None:
        """Clear all active alert state from the engine and all detectors.

        Call this after manual priming to discard alerts accumulated during
        history replay, so real data starts with a clean slate.
        """
        self.active_alerts.clear()
        for detector in self._all_detectors():
            detector.reset()

    def clear_alert(self, symbol: AssetSymbol, detector_id: str) -> AlertChange | None:
        """
        Externally dismiss an active alert.

        Clears the detector's state and removes it from active_alerts.
        Returns an AlertChange("cleared", ...) so the caller can publish AlertCleared.
        """
        key = (symbol, detector_id)
        existing = self.active_alerts.get(key)
        if existing is None:
            return None

        # Find the detector and clear its state
        for detector in self._all_detectors():
            if detector.detector_id == detector_id:
                detector.clear(symbol)
                break

        del self.active_alerts[key]
        return AlertChange("cleared", existing)

    def _all_detectors(self) -> list[Detector]:
        seen: set[int] = set()
        result: list[Detector] = []
        for d in self.default_detectors:
            if id(d) not in seen:
                seen.add(id(d))
                result.append(d)
        for detectors in self.asset_detectors.values():
            for d in detectors:
                if id(d) not in seen:
                    seen.add(id(d))
                    result.append(d)
        return result

    async def prime(
        self,
        symbols: list[AssetSymbol],
        data_provider: DataProvider,
        current_time: datetime,
        sample_interval: timedelta,
    ) -> None:
        """Prime all detectors for all given symbols.

        For each symbol, computes the maximum history age needed across all
        applicable detectors, fetches that range once, and feeds it to each
        detector via update(). Calls reset_state() after all symbols are
        processed so no alerts accumulated during priming are propagated.

        Set PRIME_SEQUENTIALLY=True to fetch symbols one at a time (useful
        for debugging or when rate-limiting is a concern).
        """
        logger.info("Priming detectors for symbols: %s", ", ".join(str(s) for s in symbols))

        def to_timedelta(age: timedelta | int) -> timedelta:
            if isinstance(age, timedelta):
                return age
            else:
                return age * sample_interval

        async def prime_symbol(symbol: AssetSymbol) -> None:
            detectors = self._detectors_for_symbol(symbol)
            if not detectors:
                return
            max_age = max(to_timedelta(d.prime_age()) for d in detectors)
            from_ = current_time - max_age
            logger.debug(
                "Priming %s: fetching %d minutes of history",
                symbol,
                int(max_age.total_seconds() / 60),
            )
            aggs = await data_provider.get_range(symbol, from_, current_time, cache_write=True, cache_read=False)
            for agg in aggs:
                for detector in detectors:
                    detector.update(agg)

        if PRIME_SEQUENTIALLY:
            for symbol in symbols:
                await prime_symbol(symbol)
        else:
            await asyncio.gather(*(prime_symbol(symbol) for symbol in symbols))

        self.reset_state()

    def _detectors_for_symbol(self, symbol: AssetSymbol) -> list[Detector]:
        """All detectors that would apply to a given symbol."""
        return self.default_detectors + self.asset_detectors.get(symbol, [])
