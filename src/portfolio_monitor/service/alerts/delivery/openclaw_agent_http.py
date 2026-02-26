from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from portfolio_monitor.data.aggregate_cache import _PRICE_PRECISION
from portfolio_monitor.detectors.base import Alert, _round_floats

logger = logging.getLogger(__name__)


class OpenClawAgentHttpDelivery:
    """Deliver alerts to an OpenClaw agent via its HTTP hook endpoint.

    Posts to ``http://{host}:{port}/hooks/agent`` with a Bearer token
    and a JSON body containing the alert as a serialized message.
    """

    # Maps python __init__ kwarg names → JSON payload keys.
    _OPTIONAL_FIELDS: dict[str, str] = {
        "name": "name",
        "session_key": "sessionKey",
        "deliver": "deliver",
        "channel": "channel",
        "wake_mode": "wakeMode",
        "to": "to",
        "model": "model",
        "thinking": "thinking",
        "timeout_seconds": "timeoutSeconds",
    }

    def __init__(
        self,
        host: str,
        port: int,
        auth_key: str,
        agent_id: str,
        *,
        name: str | None = None,
        session_key: str | None = None,
        deliver: bool = False,
        channel: str | None = None,
        wake_mode: str | None = None,
        to: str | None = None,
        model: str | None = None,
        thinking: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._url: str = f"http://{host}:{port}/hooks/agent"
        self._auth_key: str = auth_key

        # Build the static payload fields (message is added per-alert)
        kwargs = locals()
        self._payload_base: dict[str, Any] = {"agentId": agent_id}
        for kwarg, json_key in self._OPTIONAL_FIELDS.items():
            value = kwargs[kwarg]
            if value is not None:
                self._payload_base[json_key] = value

        self._client: httpx.AsyncClient | None = None

    async def send_alert(self, alert: Alert) -> None:
        if self._client is None:
            logger.warning("OpenClawAgentHttpDelivery not connected, dropping alert")
            return

        payload = {**self._payload_base, "message": json.dumps(_compact_alert(alert))}

        try:
            response = await self._client.post(
                self._url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._auth_key}",
                    "Content-Type": "application/json",
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "OpenClaw hook returned %d: %s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("OpenClaw hook request failed: %s", exc)

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info("OpenClawAgentHttpDelivery connected → %s", self._url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("OpenClawAgentHttpDelivery disconnected")


def _compact_alert(alert: Alert) -> dict[str, Any]:
    """Serialize an alert in a compact form for LLM consumption.

    Removes duplicate fields (symbol, date) that appear in both
    the alert and the embedded aggregate.
    """
    agg = alert.aggregate
    p = _PRICE_PRECISION.get(agg.symbol.asset_type, 6)
    return {
        "kind": alert.kind,
        "message": alert.message,
        "ticker": alert.ticker.to_dict(),
        "at": alert.at.isoformat(),
        "extra": _round_floats(alert.extra),
        "ohlcv": {
            "open": round(agg.open, p),
            "high": round(agg.high, p),
            "low": round(agg.low, p),
            "close": round(agg.close, p),
            "volume": round(agg.volume, 2),
            "timespan_sec": agg.timespan.total_seconds(),
        },
    }
