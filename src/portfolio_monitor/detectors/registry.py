import logging
from typing import Any, Type

from .base import Detector, DetectorInfo

logger = logging.getLogger(__name__)

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
        cls._registry[detector_class.name()] = detector_class
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
        """List all registered detector kinds."""
        return list(cls._registry.keys())

    @classmethod
    def get_detector_info(cls, kind: str) -> DetectorInfo | None:
        """Return the DetectorInfo for a registered kind, or None."""
        detector_class = cls._registry.get(kind)
        return detector_class.detector_info() if detector_class is not None else None

    @classmethod
    def list_detector_infos(cls) -> list[DetectorInfo]:
        """Return DetectorInfo for every registered detector."""
        return [klass.detector_info() for klass in cls._registry.values()]