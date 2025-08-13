from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Protocol, Type, Any

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    ticker: AssetSymbol
    kind: str
    magnitude: float
    message: str
    at: datetime
    aggregate: Aggregate  # The price aggregate that triggered the alert

class Detector(Protocol):
    @property
    def name(self) -> str:
        """Return the detector's name (used for alert kind)"""
        ...
    
    def update(self, aggregate: Aggregate) -> Alert | None:
        """Update the detector with the latest aggregate and return an alert if triggered"""
        ...


class DetectorRegistry:
    """Registry for detector classes that allows creating detectors from kind and config"""
    
    _registry: dict[str, Type[Detector]] = {}
    
    @classmethod
    def register(cls, detector_class: Type[Detector]) -> Type[Detector]:
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
    def create_detector(cls, kind: str, config: dict[str, Any] | None = None) -> Detector | None:
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