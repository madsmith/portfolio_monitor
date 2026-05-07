"""ChannelPool: shared AlertDelivery instances keyed by (type, config)."""
import logging
from typing import Any

from portfolio_monitor.service.alerts.delivery.base import AlertDelivery
from portfolio_monitor.service.alerts.delivery.logging import LoggingAlertDelivery
from portfolio_monitor.service.alerts.delivery.matrix import MatrixDelivery

logger = logging.getLogger(__name__)


def _pool_key(channel_type: str, config: dict[str, Any]) -> tuple:
    return (channel_type, frozenset(config.items()))


class ChannelPool:
    """Manages shared AlertDelivery instances, one per unique (type, config) pair.

    Two users pointing at the same Matrix room with the same access_token share
    one MatrixDelivery instance (one HTTP client) rather than opening two.
    Pool entries are connected lazily on first use via ensure_connected().
    """

    def __init__(self) -> None:
        self._pool: dict[tuple, AlertDelivery] = {}

    def get(self, channel_type: str, config: dict[str, Any]) -> AlertDelivery | None:
        """Return existing or create new delivery for this (type, config) pair."""
        key = _pool_key(channel_type, config)
        if key not in self._pool:
            instance = self._create(channel_type, config)
            if instance is None:
                return None
            self._pool[key] = instance
        return self._pool[key]

    async def ensure_connected(self, channel_type: str, config: dict[str, Any]) -> AlertDelivery | None:
        """get() and connect() the delivery if it was just created."""
        key = _pool_key(channel_type, config)
        existed = key in self._pool
        delivery = self.get(channel_type, config)
        if delivery is not None and not existed:
            try:
                await delivery.connect()
            except Exception:
                logger.exception("Failed to connect new pool entry type=%r", channel_type)
                del self._pool[key]
                return None
        return delivery

    async def connect_all(self) -> None:
        failed: list[tuple] = []
        for key, delivery in self._pool.items():
            try:
                await delivery.connect()
            except Exception:
                logger.exception("Failed to connect pool entry %s — removing", key)
                failed.append(key)
        for k in failed:
            del self._pool[k]

    async def disconnect_all(self) -> None:
        for delivery in self._pool.values():
            try:
                await delivery.disconnect()
            except Exception:
                logger.exception("Error disconnecting pool entry")
        self._pool.clear()

    def _create(self, channel_type: str, config: dict[str, Any]) -> AlertDelivery | None:
        if channel_type == "matrix":
            try:
                return MatrixDelivery.from_channel_params(config)
            except (KeyError, TypeError):
                logger.error("Invalid Matrix channel config: %s", list(config))
                return None
        elif channel_type == "logging":
            return LoggingAlertDelivery()
        # openclaw_http / openclaw_ws: deferred
        logger.warning("No delivery factory for channel type %r", channel_type)
        return None
