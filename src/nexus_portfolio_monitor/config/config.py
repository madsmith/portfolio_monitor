from typing import Any

from appconf import AppConfig, Bind


class PortfolioMonitorConfig(AppConfig):
    """Typed configuration for the Portfolio Monitor application.

    Bind descriptors provide type-safe access to well-known config keys.
    The get() method provides raw access for dynamic/variadic config
    sections like per-ticker monitor overrides.
    """

    portfolio_path = Bind[str]("portfolio_monitor.portfolio_path")
    aggregate_cache_path = Bind[str]("portfolio_monitor.aggregate_cache_path")
    polygon_api_key = Bind[str]("polygon.api_key")
    polygon_delay = Bind[int]("polygon.delay", default=15 * 60)

    def get(self, key: str, default: Any = None) -> Any:
        """Raw key lookup for dynamic config sections.

        Use this for variadic config like per-ticker monitor overrides
        that cannot be modeled as Bind descriptors.
        """
        return self._store.get(key, default)
