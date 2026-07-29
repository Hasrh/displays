"""Authenticated WebSocket server and synthetic transport stream."""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.typing import Subprotocol

from pc.config import HostConfig
from pc.state import SyntheticStateSource
from shared.constants import MAX_JSON_MESSAGE_BYTES, MessageType
from shared.protocol import (
    CommandPayload,
    CommandResultPayload,
    Envelope,
    ErrorPayload,
    HelloPayload,
    Payload,
    PingPayload,
    ProtocolError,
    StatePatchPayload,
    StateSnapshotPayload,
    WelcomePayload,
    decode_envelope,
    encode_envelope,
    negotiate_version,
    new_envelope,
)

LOGGER = logging.getLogger(__name__)
SUBPROTOCOL = Subprotocol("desktop-display.v1")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class AuthenticationError(ProtocolError):
    def __init__(self) -> None:
        super().__init__("AUTHENTICATION_FAILED", "authentication failed")


class OutboundSession:
    """Serializes writes and owns the server-to-client sequence."""

    def __init__(self, connection: ServerConnection) -> None:
        self.connection = connection
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def send(self, message_type: MessageType, payload: Payload) -> Envelope:
        async with self._lock:
            envelope = new_envelope(
                message_type,
                payload,
                sequence=self._sequence,
            )
            self._sequence += 1
            await self.connection.send(encode_envelope(envelope).decode("utf-8"))
            return envelope


class WebSocketHost:
    """One-host, multiple-renderer WebSocket service."""

    def __init__(
        self,
        config: HostConfig,
        auth_token: str,
        *,
        state_source: SyntheticStateSource | None = None,
    ) -> None:
        if len(auth_token) < 16:
            raise ValueError("authentication token must contain at least 16 characters")
        self.config = config
        self._auth_token = auth_token
        self._state_source = state_source or SyntheticStateSource()

    async def run(
        self,
        stop_event: asyncio.Event | None = None,
        started_event: asyncio.Event | None = None,
    ) -> None:
        async with serve(
            self._handle_connection,
            self.config.bind_host,
            self.config.port,
            subprotocols=[SUBPROTOCOL],
            compression=None,
            ping_interval=None,
            max_size=MAX_JSON_MESSAGE_BYTES,
            max_queue=4,
        ) as server:
            LOGGER.info(
                "WebSocket host listening on ws://%s:%d",
                self.config.bind_host,
                self.config.port,
            )
            if started_event is not None:
                started_event.set()
            if stop_event is None:
                await server.serve_forever()
            else:
                await stop_event.wait()

    async def _handle_connection(self, connection: ServerConnection) -> None:
        peer = str(connection.remote_address)
        if connection.subprotocol != SUBPROTOCOL:
            await connection.close(1002, "required subprotocol not negotiated")
            return

        sender = OutboundSession(connection)
        try:
            hello = await self._receive_hello(connection)
            selected_version = negotiate_version(hello.supported_versions)
            if hello.auth_token is None or not hmac.compare_digest(
                hello.auth_token, self._auth_token
            ):
                raise AuthenticationError

            await sender.send(
                MessageType.WELCOME,
                WelcomePayload(
                    session_id=connection.id.hex,
                    selected_version=selected_version,
                    heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
                    max_json_message_bytes=MAX_JSON_MESSAGE_BYTES,
                ),
            )
            started = monotonic()
            snapshot = await sender.send(
                MessageType.STATE_SNAPSHOT,
                StateSnapshotPayload(
                    generated_at=_utc_now(),
                    state=self._state_source.state_at(0.0),
                ),
            )
            LOGGER.info(
                "Renderer connected client_id=%s peer=%s protocol=%s display=%dx%d",
                hello.client_id,
                peer,
                selected_version,
                hello.capabilities.width,
                hello.capabilities.height,
            )
            await self._run_session(
                connection,
                sender,
                snapshot.sequence,
                started,
                min(30, hello.capabilities.target_fps),
            )
        except AuthenticationError as exc:
            await self._send_error(sender, exc)
            await connection.close(1008, exc.code)
            LOGGER.warning("Rejected unauthenticated renderer peer=%s", peer)
        except ProtocolError as exc:
            await self._send_error(sender, exc)
            await connection.close(1008, exc.code)
            LOGGER.warning("Protocol rejection peer=%s code=%s", peer, exc.code)
        except ConnectionClosed:
            pass
        finally:
            LOGGER.info("Renderer disconnected peer=%s", peer)

    async def _receive_hello(self, connection: ServerConnection) -> HelloPayload:
        try:
            raw = await asyncio.wait_for(
                connection.recv(),
                timeout=self.config.client_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProtocolError("HANDSHAKE_TIMEOUT", "hello message was not received") from exc
        if not isinstance(raw, str):
            raise ProtocolError("EXPECTED_TEXT", "hello must be a JSON text message")
        envelope = decode_envelope(raw)
        if envelope.type is not MessageType.HELLO or not isinstance(envelope.payload, HelloPayload):
            raise ProtocolError("EXPECTED_HELLO", "first message must be hello")
        return envelope.payload

    async def _run_session(
        self,
        connection: ServerConnection,
        sender: OutboundSession,
        snapshot_sequence: int,
        started: float,
        fft_fps: int,
    ) -> None:
        last_client_message = [monotonic()]
        tasks = {
            asyncio.create_task(
                self._stream_synthetic(sender, snapshot_sequence, started, fft_fps)
            ),
            asyncio.create_task(self._receive_messages(connection, sender, last_client_message)),
            asyncio.create_task(self._heartbeat(connection, sender, last_client_message)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()

    async def _stream_synthetic(
        self,
        sender: OutboundSession,
        snapshot_sequence: int,
        started: float,
        fft_fps: int,
    ) -> None:
        fft_interval = 1.0 / max(1, fft_fps)
        next_fft = monotonic()
        next_state = monotonic() + 0.5
        while True:
            now = monotonic()
            elapsed = now - started
            if now >= next_state:
                state = self._state_source.state_at(elapsed)
                await sender.send(
                    MessageType.STATE_PATCH,
                    StatePatchPayload(
                        base_sequence=snapshot_sequence,
                        changes={
                            "media": state.media.to_dict() if state.media else None,
                            "system": state.system.to_dict() if state.system else None,
                            "network": state.network.to_dict() if state.network else None,
                        },
                    ),
                )
                next_state = now + 0.5
            if now >= next_fft:
                await sender.send(
                    MessageType.FFT_FRAME,
                    self._state_source.fft_at(elapsed, _utc_now()),
                )
                next_fft = now + fft_interval
            await asyncio.sleep(max(0.001, min(next_fft, next_state) - monotonic()))

    async def _receive_messages(
        self,
        connection: ServerConnection,
        sender: OutboundSession,
        last_client_message: list[float],
    ) -> None:
        async for raw in connection:
            if not isinstance(raw, str):
                raise ProtocolError("EXPECTED_TEXT", "client messages must be JSON text")
            envelope = decode_envelope(raw)
            last_client_message[0] = monotonic()
            if envelope.type is MessageType.PONG:
                continue
            if envelope.type is MessageType.PING and isinstance(envelope.payload, PingPayload):
                await sender.send(MessageType.PONG, envelope.payload)
            elif envelope.type is MessageType.COMMAND and isinstance(
                envelope.payload, CommandPayload
            ):
                await sender.send(
                    MessageType.COMMAND_RESULT,
                    CommandResultPayload(
                        command_id=envelope.payload.command_id,
                        success=False,
                        error_code="NOT_IMPLEMENTED",
                        message="command handlers are not implemented",
                    ),
                )
            else:
                await sender.send(
                    MessageType.ERROR,
                    ErrorPayload(
                        code="UNEXPECTED_MESSAGE",
                        message=f"host cannot accept {envelope.type.value}",
                        retryable=False,
                    ),
                )

    async def _heartbeat(
        self,
        connection: ServerConnection,
        sender: OutboundSession,
        last_client_message: list[float],
    ) -> None:
        while True:
            await asyncio.sleep(self.config.heartbeat_interval_seconds)
            if monotonic() - last_client_message[0] > self.config.client_timeout_seconds:
                await connection.close(1011, "client heartbeat timeout")
                return
            await sender.send(MessageType.PING, PingPayload(nonce=str(monotonic_ns())))

    @staticmethod
    async def _send_error(sender: OutboundSession, error: ProtocolError) -> None:
        with suppress(ConnectionClosed):
            await sender.send(
                MessageType.ERROR,
                ErrorPayload(code=error.code, message=error.message, retryable=False),
            )


def monotonic_ns() -> int:
    """Isolated for deterministic test replacement."""

    return int(monotonic() * 1_000_000_000)
