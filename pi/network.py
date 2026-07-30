"""Reconnecting WebSocket client for the Raspberry Pi renderer."""

from __future__ import annotations

import asyncio
import logging
import random
from contextlib import suppress

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.typing import Subprotocol

from pi.assets import AssetCache
from pi.config import PiConfig
from pi.state import LatestStateStore
from shared.constants import MAX_ASSET_BYTES, MAX_JSON_MESSAGE_BYTES, PROTOCOL_VERSION, MessageType
from shared.models import DisplayCapabilities
from shared.protocol import (
    ErrorPayload,
    HelloPayload,
    Payload,
    PingPayload,
    ProtocolError,
    WelcomePayload,
    decode_asset_frame,
    decode_envelope,
    encode_envelope,
    new_envelope,
)

LOGGER = logging.getLogger(__name__)
SUBPROTOCOL = Subprotocol("desktop-display.v1")


class PiNetworkClient:
    """Maintains one authenticated connection and latest-value state."""

    def __init__(
        self,
        config: PiConfig,
        auth_token: str,
        store: LatestStateStore,
        assets: AssetCache | None = None,
    ) -> None:
        if len(auth_token) < 16:
            raise ValueError("authentication token must contain at least 16 characters")
        self.config = config
        self._auth_token = auth_token
        self.store = store
        self.assets = assets
        self._outbound_sequence = 0
        self._send_lock = asyncio.Lock()

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        """Reconnect until cancelled or the optional stop event is set."""

        stop = stop_event or asyncio.Event()
        attempt = 0
        while not stop.is_set():
            try:
                await self._run_connection(stop)
                attempt = 0
            except asyncio.CancelledError:
                raise
            except (
                ConnectionClosed,
                InvalidHandshake,
                InvalidURI,
                OSError,
                ProtocolError,
                TimeoutError,
            ) as exc:
                self.store.set_connected(False)
                delay = min(
                    self.config.reconnect_max_seconds,
                    self.config.reconnect_initial_seconds * (2**attempt),
                )
                delay += random.uniform(0.0, delay * 0.2)
                attempt = min(attempt + 1, 16)
                LOGGER.warning(
                    "Connection unavailable (%s); retrying in %.1fs",
                    exc,
                    delay,
                )
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
            finally:
                self.store.set_connected(False)

    async def _run_connection(self, stop_event: asyncio.Event) -> None:
        self._outbound_sequence = 0
        self.store.reset_session()
        async with connect(
            self.config.host_url,
            subprotocols=[SUBPROTOCOL],
            compression=None,
            proxy=None,
            open_timeout=self.config.handshake_timeout_seconds,
            ping_interval=None,
            max_size=MAX_ASSET_BYTES + MAX_JSON_MESSAGE_BYTES,
            max_queue=4,
        ) as connection:
            if connection.subprotocol != SUBPROTOCOL:
                raise ProtocolError("SUBPROTOCOL_MISMATCH", "server rejected protocol")
            await self._send_hello(connection)
            await self._receive_welcome(connection)
            self.store.set_connected(True)
            LOGGER.info("Connected to host at %s", self.config.host_url)

            async for raw in connection:
                if stop_event.is_set():
                    await connection.close(1000, "client stopping")
                    return
                if isinstance(raw, bytes):
                    asset = decode_asset_frame(raw)
                    if self.assets is not None and self.assets.store(asset):
                        LOGGER.info(
                            "Cached album art id=%s bytes=%d",
                            asset.metadata.asset_id,
                            len(asset.data),
                        )
                    else:
                        LOGGER.info(
                            "Received asset id=%s bytes=%d",
                            asset.metadata.asset_id,
                            len(asset.data),
                        )
                    continue
                envelope = decode_envelope(raw)
                if envelope.type is MessageType.PING and isinstance(envelope.payload, PingPayload):
                    await self._send(connection, MessageType.PONG, envelope.payload)
                elif envelope.type in {
                    MessageType.STATE_SNAPSHOT,
                    MessageType.STATE_PATCH,
                    MessageType.FFT_FRAME,
                }:
                    applied = self.store.apply(envelope)
                    if applied and envelope.type is MessageType.STATE_SNAPSHOT:
                        LOGGER.info("Received authoritative state snapshot")
                elif envelope.type is MessageType.ERROR and isinstance(
                    envelope.payload, ErrorPayload
                ):
                    raise ProtocolError(envelope.payload.code, envelope.payload.message)
            if not stop_event.is_set():
                raise ProtocolError("CONNECTION_CLOSED", "host closed the connection")

    async def _send_hello(self, connection: ClientConnection) -> None:
        await self._send(
            connection,
            MessageType.HELLO,
            HelloPayload(
                client_id=self.config.client_id,
                supported_versions=(PROTOCOL_VERSION,),
                capabilities=DisplayCapabilities(
                    width=self.config.width,
                    height=self.config.height,
                    orientation=self.config.orientation,
                    target_fps=self.config.target_fps,
                    touch_enabled=self.config.touch_controller is not None,
                ),
                auth_token=self._auth_token,
            ),
        )

    async def _receive_welcome(self, connection: ClientConnection) -> WelcomePayload:
        try:
            raw = await asyncio.wait_for(
                connection.recv(),
                timeout=self.config.handshake_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProtocolError("HANDSHAKE_TIMEOUT", "welcome message was not received") from exc
        if not isinstance(raw, str):
            raise ProtocolError("EXPECTED_TEXT", "welcome must be a JSON text message")
        envelope = decode_envelope(raw)
        if envelope.type is MessageType.ERROR and isinstance(envelope.payload, ErrorPayload):
            raise ProtocolError(envelope.payload.code, envelope.payload.message)
        if envelope.type is not MessageType.WELCOME or not isinstance(
            envelope.payload, WelcomePayload
        ):
            raise ProtocolError("EXPECTED_WELCOME", "first server message must be welcome")
        return envelope.payload

    async def _send(
        self,
        connection: ClientConnection,
        message_type: MessageType,
        payload: Payload,
    ) -> None:
        async with self._send_lock:
            envelope = new_envelope(
                message_type,
                payload,
                sequence=self._outbound_sequence,
            )
            self._outbound_sequence += 1
            await connection.send(encode_envelope(envelope).decode("utf-8"))
