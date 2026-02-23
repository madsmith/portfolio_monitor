import logging

from datetime import datetime, timedelta
from typing import Any, Sequence

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.detectors import Alert, Detector, DetectorRegistry
from portfolio_monitor.service.types import AssetSymbol

DetectorSpec = Detector | dict[str, Any]

logger = logging.getLogger(__name__)

class DeviationEngine:
    """
    Engine that manages multiple detectors and processes aggregates through them
    to generate alerts based on detected price deviations.
    """

    def __init__(
        self,
        default_detectors: Sequence[DetectorSpec] | None = None,
        cooldown: timedelta = timedelta(minutes=15)
    ):
        """
        Initialize the deviation engine.
        
        Args:
            default_detectors: List of detector instances that apply to all assets
            cooldown: Time to wait before generating another alert of same type for a ticker
        """
        self.cooldown = cooldown
        self.last_alert_at: dict[tuple[AssetSymbol, str], datetime] = {}
        self.default_detectors: list[Detector] = []
        if default_detectors:
            for detector in default_detectors:
                if isinstance(detector, Detector):
                    self.default_detectors.append(detector)
                elif isinstance(detector, dict):
                    d = DetectorRegistry.create_detector(detector["name"], detector.get("args"))
                    if d is not None:
                        self.default_detectors.append(d)
                    else:
                        raise ValueError(f"Invalid detector: {detector}")
                else:
                    raise ValueError(f"Type {type(detector)} is not a valid detector")
        
        self.asset_detectors: dict[AssetSymbol, list[Detector]] = {}
        
    def add_detector(self, symbol: AssetSymbol, detector: DetectorSpec) -> None:
        """
        Add a detector for a specific asset symbol.
        
        Args:
            symbol: Asset symbol the detector should apply to
            detector: Detector instance
        """
        if symbol not in self.asset_detectors:
            self.asset_detectors[symbol] = []
        

        if isinstance(detector, Detector):
            self.asset_detectors[symbol].append(detector)
        elif isinstance(detector, dict):
            d = DetectorRegistry.create_detector(detector["name"], detector.get("args"))
            if d is not None:
                self.asset_detectors[symbol].append(d)
            else:
                raise ValueError(f"Invalid detector: {detector}")
        else:
            raise ValueError(f"Type {type(detector)} is not a valid detector")
    
    def get_available_detector_kinds(self) -> list[str]:
        """
        Get a list of all registered detector kinds that can be created.
        
        Returns:
            List of detector kind strings
        """
        return DetectorRegistry.list_available_detectors()

    def detect(self, aggregate: Aggregate) -> list[Alert]:
        """
        Process an aggregate through all applicable detectors and return any alerts.
        
        Args:
            aggregate: Price aggregate to process
            
        Returns:
            List of alerts generated (empty if no alerts)
        """
        ticker = aggregate.symbol
        alerts: list[Alert] = []
        
        # Process through default detectors (apply to all assets)
        for detector in self.default_detectors:
            alert = detector.update(aggregate)
            if alert and self._check_cooldown(alert):
                alerts.append(alert)
        
        # Process through asset-specific detectors if any
        if ticker in self.asset_detectors:
            for detector in self.asset_detectors[ticker]:
                alert = detector.update(aggregate)
                if alert and self._check_cooldown(alert):
                    alerts.append(alert)
                    
        return alerts
    
    def clear_cooldowns(self):
        self.last_alert_at.clear()
    
    def _check_cooldown(self, alert: Alert) -> bool:
        """
        Check if the alert is within cooldown period.
        
        Args:
            alert: Alert to check
            
        Returns:
            True if alert should be processed (not in cooldown), False otherwise
        """
        key = (alert.ticker, alert.kind)
        last = self.last_alert_at.get(key)
        
        if last and (alert.at - last) < self.cooldown:
            return False  # In cooldown period, skip this alert
            
        # Update last alert time and allow this alert
        self.last_alert_at[key] = alert.at
        return True

    def preload_data_age(self, current_time: datetime, sample_interval: timedelta) -> datetime | None:
        """
        Calculate the age of the data needed to prime the detection engine.
        """
        min_age: datetime | None = None
        for detector in self.default_detectors:
            age = detector.preload_data_age(current_time, sample_interval)
            if age is not None:
                if min_age is None:
                    min_age = age
                else:
                    min_age = min(min_age, age)

        for _, detectors in self.asset_detectors.items():
            for detector in detectors:
                age = detector.preload_data_age(current_time, sample_interval)
                if age is not None:
                    if min_age is None:
                        min_age = age
                    else:
                        min_age = min(min_age, age)
        return min_age
        