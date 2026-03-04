from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import uuid
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

from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.service.alerts.delivery.openclaw_agent_http import _compact_alert

logger = logging.getLogger(__name__)


class NoncePayload(BaseModel):
    nonce: str
    ts: int


class ChallengeEvent(BaseModel):
    type: str = "event"
    event: str = "connect.challenge"
    payload: NoncePayload


class OpenClawGatewayWsDelivery:
    """Deliver alerts to an OpenClaw agent via the Gateway WebSocket protocol.

    Connects to ``ws://{host}:{port}`` and sends alerts using the gateway's
    frame protocol (connect handshake, then ``agent`` method frames).
    """

    # Maps python __init__ kwarg names → JSON payload keys for agent frames.
    _OPTIONAL_FIELDS: dict[str, str] = {
        "session_key": "sessionKey",
        "deliver": "deliver",
        "channel": "channel",
        "to": "to",
        "thinking": "thinking",
        "timeout_seconds": "timeout",
        "extra_prompt": "extraSystemPrompt",
    }

    def __init__(
        self,
        host: str,
        port: int,
        agent_id: str,
        *,
        gateway_token: str | None = None,
        gateway_password: str | None = None,
        device_identity_file: Path | None = None,
        name: str | None = None,
        session_key: str | None = None,
        deliver: bool = False,
        channel: str | None = None,
        to: str | None = None,
        thinking: str | None = None,
        timeout_seconds: int | None = None,
        extra_prompt: str | None = None
    ) -> None:
        if not gateway_token and not gateway_password:
            raise ValueError(
                "Either gateway_token or gateway_password must be provided"
            )

        self.device_identity: dict[str, str] | None = None
        if device_identity_file is not None:
            self.load_device_identity(device_identity_file)

        self._ws_url: str = f"ws://{host}:{port}"
        self._auth: dict[str, str] = (
            {"token": gateway_token}
            if gateway_token
            else {"password": gateway_password}  # type: ignore[dict-item]
        )
        self._name: str | None = name

        # Build static agent-method params (message + idempotencyKey added per-alert)
        kwargs = locals()
        self._agent_params_base: dict[str, Any] = {"agentId": agent_id}
        for kwarg, json_key in self._OPTIONAL_FIELDS.items():
            value = kwargs[kwarg]
            if value is not None:
                # Gateway expects sessionKey in the format "agent:{agent_id}:{session_key}"
                if json_key == "sessionKey":
                    value = f"agent:{agent_id}:{value}"
                self._agent_params_base[json_key] = value

        self._ws: ClientConnection | None = None
        self._reader_task: asyncio.Task | None = None
        self._connected: bool = False
        self._connect_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Device identity
    # ------------------------------------------------------------------

    def generate_device_identity(self, path: Path) -> dict[str, str]:
        """Generate an Ed25519 keypair and save the device identity to *path*."""
        private_key = Ed25519PrivateKey.generate()
        private_pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode()
        public_pem = (
            private_key.public_key()
            .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )

        # Device ID = SHA-256 of the raw 32-byte public key
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
        self.device_identity = identity
        return identity

    def load_device_identity(self, path: Path) -> dict[str, str]:
        """Load device identity from *path*, generating it if missing."""
        if path.exists():
            with open(path) as f:
                identity: dict[str, str] = json.load(f)
            logger.info(
                "Loaded device identity %s ← %s",
                identity["deviceId"][:12],
                path,
            )
            self.device_identity = identity
            return identity
        return self.generate_device_identity(path)

    async def connect(self) -> None:
        """Open WebSocket, send connect frame, verify hello-ok."""
        await self._do_connect()
        logger.info("OpenClawGatewayWsDelivery connected → %s", self._ws_url)

    async def disconnect(self) -> None:
        """Close WebSocket and cancel reader task."""
        await self._do_disconnect()
        logger.info("OpenClawGatewayWsDelivery disconnected")

    async def send_alert(self, alert: Alert) -> None:
        """Send an alert as a gateway ``agent`` method frame."""
        if not self._connected or self._ws is None:
            async with self._connect_lock:
                if not self._connected or self._ws is None:
                    logger.warning("WebSocket not connected, attempting reconnect…")
                    try:
                        await self._do_connect()
                        assert self._ws is not None
                    except Exception as exc:
                        logger.warning("Reconnect failed, dropping alert: %s", exc)
                        return

        idempotency_key = str(uuid.uuid4())
        frame = {
            "type": "req",
            "id": f"alert-{idempotency_key}",
            "method": "agent",
            "params": {
                **self._agent_params_base,
                "message": json.dumps(_compact_alert(alert)),
                "idempotencyKey": idempotency_key,
            },
        }
        if self._name:
            frame["params"]["label"] = self._name

        try:
            logger.info(
                "Sending Gateway Alert: [%s] %s", alert.ticker.ticker, alert.kind
            )
            print(f"!!!!Sending Gateway Alert: {frame}")
            await self._ws.send(json.dumps(frame))
        except Exception as exc:
            logger.warning("Failed to send alert frame: %s", exc)
            self._connected = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_connect(self) -> None:
        """Open WS, perform handshake, start reader."""
        await self._do_disconnect()

        self._ws = await websockets.connect(self._ws_url)

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            challenge_json = json.loads(raw)
            challenge = ChallengeEvent.model_validate(challenge_json)

        except json.JSONDecodeError:
            logger.warning("Failed to decode challenge")
            self._connected = False
            return

        client_id = "gateway-client"
        mode = "backend"
        role = "operator"

        device_field = self._build_device_field(
            challenge.payload.nonce,
            client_id,
            mode,
            role,
            ["operator.read", "operator.write"],
        )

        connect_frame = {
            "type": "req",
            "id": "connect-1",
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": client_id,
                    "version": "1.0.0",
                    "platform": "python",
                    "mode": mode,
                },
                "device": device_field,
                "auth": self._auth,
                "role": role,
                "scopes": ["operator.read", "operator.write"],
            },
        }
        await self._ws.send(json.dumps(connect_frame))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        response = json.loads(raw)
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
        """Build the ``device`` field for the connect frame.

        Signs a v2 payload with the Ed25519 private key from
        ``self.device_identity`` and returns the dict to embed
        in ``connect_frame["params"]["device"]``.
        """
        assert self.device_identity is not None
        identity = self.device_identity

        signed_at_ms = int(time.time() * 1000)
        scope_str = ",".join(scopes)

        payload = "|".join(
            [
                "v2",
                identity["deviceId"],
                client_id,  # client.id
                mode,  # client.mode
                role,  # role
                scope_str,
                str(signed_at_ms),
                self._auth.get("token", ""),
                nonce,
            ]
        )

        private_key = load_pem_private_key(
            identity["privateKeyPem"].encode(), password=None
        )
        assert isinstance(private_key, Ed25519PrivateKey), (
            "Expected Ed25519 Private Key"
        )
        signature = private_key.sign(payload.encode("utf-8"))

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
        """Cancel reader and close WS."""
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
        """Drain incoming messages to prevent buffer buildup.

        Responses and tick events are discarded. If the connection
        drops, ``_connected`` is cleared so the next ``send_alert``
        triggers a reconnect.
        """
        assert self._ws is not None
        try:
            async for _message in self._ws:
                try:
                    msg_json = json.loads(_message)
                    if getattr(msg_json, "type", None) == "res":
                        is_ok = getattr("msg_json", "ok", None)
                        # explicit check against False to ignore is_ok == None when ok not found
                        if is_ok == False:  # noqa: E712
                            error = getattr(msg_json, "error", None)
                            if error:
                                error_msg = getattr(msg_json, "message", None)
                                if error_msg:
                                    logger.error(
                                        "Gateway WebSocket error: %s - %s",
                                        error,
                                        error_msg,
                                    )
                                else:
                                    logger.error("Gateway WebSocket error: %s", error)
                            else:
                                logger.error("Gateway WebSocket error: Unknown")
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to decode message: %s", exc)
                    continue
                pass  # discard responses and tick events
        except websockets.ConnectionClosed:
            logger.warning("Gateway WebSocket connection closed")
            self._connected = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Gateway WebSocket reader error: %s", exc)
            self._connected = False
