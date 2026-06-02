"""OpenClaw Gateway WebSocket alert delivery."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import websockets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)
from pydantic import BaseModel
from websockets.asyncio.client import ClientConnection

from portfolio_monitor import __version__
from portfolio_monitor.detectors import Alert
from portfolio_monitor.service.alerts.delivery.openclaw_agent_http import _compact_alert
from .base import AlertDelivery, AlertEventType

logger = logging.getLogger(__name__)


class _NoncePayload(BaseModel):
    nonce: str
    ts: int


class _ChallengeEvent(BaseModel):
    type: str = "event"
    event: str = "connect.challenge"
    payload: _NoncePayload


class OpenClawWsDelivery:
    """Deliver alerts to an OpenClaw agent via the Gateway WebSocket protocol.

    Connects to ``ws://{host}:{port}`` and sends alerts as ``agent`` method
    frames after completing the connect handshake.

    Admin channel config params (connection only):
        host                 — gateway hostname (default: 127.0.0.1)
        port                 — gateway port (default: 18789)
        gateway_token        — bearer token auth (provide this or gateway_password)
        gateway_password     — password auth (provide this or gateway_token)
        device_identity_file — server-side path to Ed25519 identity JSON file;
                               auto-generated at that path if absent
                               (default: ./config/device_identity.json)

    Per-user subscription ``target``:
        Either a plain agent ID string, or a JSON object with any of::

            {
              "agentId": "finance",
              "sessionKey": "main",
              "extraPrompt": "Focus on high-volatility alerts.",
              "thinking": "low",
              "bootstrapContextMode": "lightweight",
              "bootstrapContextRunKind": "cron",
              "deliver": false,
              "channel": "matrix",
              "timeout": 60
            }

        ``sessionKey`` is sent verbatim if it starts with ``"agent:"``, otherwise
        namespaced as ``agent:{agentId}:{sessionKey}``.
        Defaults: ``deliver=false``, ``bootstrapContextMode="lightweight"``,
        ``bootstrapContextRunKind="cron"``.
        Alerts are dropped when target is empty.

    Every frame also sets ``inputProvenance`` to
    ``{"kind": "external_user", "sourceChannel": "portfolio-monitor"}`` and a per-alert ``label``.
    The ``idempotencyKey`` is ``alert.id`` — FIRED and UPDATED events for the same
    alert share a key, so the gateway de-dups retries without spawning duplicate runs.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        gateway_token: str | None = None,
        gateway_password: str | None = None,
        device_identity_file: Path | None = None,
    ) -> None:
        if not gateway_token and not gateway_password:
            raise ValueError("Either gateway_token or gateway_password must be provided")

        self._ws_url: str = f"ws://{host}:{port}"
        self._auth: dict[str, str] = (
            {"token": gateway_token}
            if gateway_token
            else {"password": gateway_password}  # type: ignore[dict-item]
        )

        self._device_identity: dict[str, str] | None = None
        if device_identity_file is not None:
            self._device_identity = self._load_or_generate_identity(device_identity_file)

        self._ws: ClientConnection | None = None
        self._reader_task: asyncio.Task | None = None
        self._connected: bool = False
        self._connect_lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    def from_channel_params(cls, params: dict[str, Any]) -> "OpenClawWsDelivery":
        device_file = params.get("device_identity_file") or None
        return cls(
            host=params["host"],
            port=int(params["port"]),
            gateway_token=params.get("gateway_token") or None,
            gateway_password=params.get("gateway_password") or None,
            device_identity_file=Path(device_file) if device_file else None,
        )

    # ------------------------------------------------------------------
    # AlertDelivery protocol
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        await self._do_connect()
        logger.info("OpenClawWsDelivery connected → %s", self._ws_url)

    async def disconnect(self) -> None:
        await self._do_disconnect()
        logger.info("OpenClawWsDelivery disconnected")

    async def send_alert(
        self,
        alert: Alert,
        *,
        target: str = "",
        event: AlertEventType = AlertEventType.FIRED,
    ) -> None:
        if not target:
            logger.debug("OpenClawWsDelivery: no agent_id (target) specified, skipping")
            return

        # target is either a plain agent_id string or a JSON object of user-level params
        agent_id = target
        user: dict[str, Any] = {}
        if target.startswith("{"):
            try:
                user = json.loads(target)
                agent_id = user.get("agentId", "")
            except json.JSONDecodeError:
                pass

        if not agent_id:
            logger.debug("OpenClawWsDelivery: empty agentId in target, skipping")
            return

        if not self._connected or self._ws is None:
            async with self._connect_lock:
                if not self._connected or self._ws is None:
                    logger.warning("WebSocket not connected, attempting reconnect…")
                    try:
                        await self._do_connect()
                    except Exception as exc:
                        logger.warning("Reconnect failed, dropping alert: %s", exc)
                        return

        # Stable idempotency key: FIRED and UPDATED for the same alert share a key so
        # the gateway de-dups retries and update noise without spawning duplicate runs.
        params: dict[str, Any] = {
            "agentId": agent_id,
            "message": json.dumps(_compact_alert(alert)),
            "idempotencyKey": alert.id,
            "label": f"Portfolio Alerts",
            "inputProvenance": {"kind": "external_user", "sourceChannel": "portfolio-monitor"},
            # User-controlled per-call params with sensible defaults
            "deliver": bool(user.get("deliver", False)),
            "bootstrapContextMode": user.get("bootstrapContextMode", "lightweight"),
            "bootstrapContextRunKind": user.get("bootstrapContextRunKind", "cron"),
        }

        if channel := user.get("channel"):
            params["channel"] = channel
        if timeout := user.get("timeout"):
            params["timeout"] = int(timeout)

        session_key: str = user.get("sessionKey", "")
        if session_key:
            params["sessionKey"] = (
                session_key if session_key.startswith("agent:")
                else f"agent:{agent_id}:{session_key}"
            )

        if extra_prompt := user.get("extraPrompt"):
            params["extraSystemPrompt"] = extra_prompt
        if thinking := user.get("thinking"):
            params["thinking"] = thinking

        frame: dict[str, Any] = {
            "type": "req",
            "id": f"alert-{alert.id}",
            "method": "agent",
            "params": params,
        }

        assert self._ws is not None
        try:
            logger.info("Sending Gateway alert: [%s] %s", alert.ticker.ticker, alert.kind)
            await self._ws.send(json.dumps(frame))
        except Exception as exc:
            logger.warning("Failed to send alert frame: %s", exc)
            self._connected = False

    # ------------------------------------------------------------------
    # Device identity
    # ------------------------------------------------------------------

    def _load_or_generate_identity(self, path: Path) -> dict[str, str]:
        if path.exists():
            with open(path) as f:
                identity: dict[str, str] = json.load(f)
            logger.info("Loaded device identity %s ← %s", identity["deviceId"][:12], path)
            return identity
        return self._generate_identity(path)

    def _generate_identity(self, path: Path) -> dict[str, str]:
        private_key = Ed25519PrivateKey.generate()
        private_pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode()
        public_pem = (
            private_key.public_key()
            .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )

        spki_der = private_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        raw_public_key = spki_der[-32:]
        device_id = hashlib.sha256(raw_public_key).hexdigest()

        identity: dict[str, str] = {
            "version": "1",
            "deviceId": device_id,
            "publicKeyPem": public_pem,
            "privateKeyPem": private_pem,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(identity, f, indent=2)
        logger.info("Generated device identity %s → %s", device_id[:12], path)
        return identity

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_connect(self) -> None:
        await self._do_disconnect()

        self._ws = await websockets.connect(self._ws_url)
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            challenge = _ChallengeEvent.model_validate(json.loads(raw))
        except Exception as exc:
            self._connected = False
            await self._ws.close()
            self._ws = None
            raise ConnectionError(f"Failed to receive challenge: {exc}") from exc

        client_id = "gateway-client"
        mode = "backend"
        role = "operator"
        scopes = ["operator.read", "operator.write"]

        connect_params: dict[str, Any] = {
            "minProtocol": 4,
            "maxProtocol": 4,
            "client": {
                "id": client_id,
                "displayName": "Portfolio Monitor",
                "version": __version__,
                "platform": "python",
                "mode": mode,
            },
            "auth": self._auth,
            "role": role,
            "scopes": scopes,
        }
        if self._device_identity is not None:
            connect_params["device"] = self._build_device_field(
                challenge.payload.nonce, client_id, mode, role, scopes
            )

        connect_frame: dict[str, Any] = {
            "type": "req",
            "id": "connect-1",
            "method": "connect",
            "params": connect_params,
        }
        await self._ws.send(json.dumps(connect_frame))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        response: dict[str, Any] = json.loads(raw)
        if not response.get("ok"):
            error = response.get("error", response)
            await self._ws.close()
            self._ws = None
            raise ConnectionError(f"Gateway handshake failed: {error}")

        self._connected = True
        self._reader_task = asyncio.create_task(
            self._reader_loop(), name="openclaw-ws-reader"
        )

    def _build_device_field(
        self, nonce: str, client_id: str, mode: str, role: str, scopes: list[str]
    ) -> dict[str, Any]:
        assert self._device_identity is not None
        identity = self._device_identity

        signed_at_ms = int(time.time() * 1000)
        payload_str = "|".join([
            "v2",
            identity["deviceId"],
            client_id,
            mode,
            role,
            ",".join(scopes),
            str(signed_at_ms),
            self._auth.get("token", ""),
            nonce,
        ])

        private_key = load_pem_private_key(identity["privateKeyPem"].encode(), password=None)
        assert isinstance(private_key, Ed25519PrivateKey)
        signature = private_key.sign(payload_str.encode("utf-8"))

        spki_der = private_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        raw_public_key = spki_der[-32:]

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        return {
            "id": identity["deviceId"],
            "publicKey": b64url(raw_public_key),
            "signature": b64url(signature),
            "signedAt": signed_at_ms,
            "nonce": nonce,
        }

    async def _do_disconnect(self) -> None:
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _reader_loop(self) -> None:
        """Drain incoming messages and log gateway errors."""
        assert self._ws is not None
        try:
            async for message in self._ws:
                try:
                    msg: dict[str, Any] = json.loads(message)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to decode gateway message: %s", exc)
                    continue
                if msg.get("type") == "res" and msg.get("ok") is False:
                    error = msg.get("error")
                    error_msg = msg.get("message")
                    if error and error_msg:
                        logger.error("Gateway error: %s - %s", error, error_msg)
                    elif error:
                        logger.error("Gateway error: %s", error)
                    else:
                        logger.error("Gateway error: unknown")
        except websockets.ConnectionClosed:
            logger.warning("Gateway WebSocket connection closed")
            self._connected = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Gateway WebSocket reader error: %s", exc)
            self._connected = False


