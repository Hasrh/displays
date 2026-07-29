"""Versioned JSON messages and binary asset framing.

The module is dependency-free so identical validation runs on Windows and the
Raspberry Pi before a message reaches application code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import struct
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeAlias

from shared.constants import (
    ASSET_FRAME_MAGIC,
    ASSET_FRAME_VERSION,
    MAX_ASSET_BYTES,
    MAX_JSON_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    CommandAction,
    MessageType,
)
from shared.models import AssetMetadata, DisplayCapabilities, DisplayState, FFTFrame

JsonObject: TypeAlias = dict[str, Any]


class ProtocolError(ValueError):
    """Safe, machine-readable protocol validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _object(value: object, field_name: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object with string keys")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(
    value: object,
    field_name: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer of at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field_name} must not exceed {maximum}")
    return value


def _number(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return number


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _timestamp(value: object, field_name: str) -> str:
    text = _string(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an RFC-3339 timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must use UTC")
    return text


def _json_value(value: object, field_name: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{field_name} must contain only finite numbers")
        return value
    if isinstance(value, list):
        return [_json_value(item, f"{field_name}[]") for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item, f"{field_name}.{key}") for key, item in value.items()}
    raise ValueError(f"{field_name} contains a value that JSON cannot represent")


@dataclass(frozen=True, slots=True)
class HelloPayload:
    client_id: str
    supported_versions: tuple[str, ...]
    capabilities: DisplayCapabilities
    auth_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, value: object) -> HelloPayload:
        data = _object(value, "hello payload")
        versions = data.get("supported_versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError("hello.supported_versions must be a non-empty list")
        return cls(
            client_id=_string(data.get("client_id"), "hello.client_id"),
            supported_versions=tuple(
                _string(version, f"hello.supported_versions[{index}]")
                for index, version in enumerate(versions)
            ),
            capabilities=DisplayCapabilities.from_dict(data.get("capabilities")),
            auth_token=_optional_string(data.get("auth_token"), "hello.auth_token"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "client_id": self.client_id,
            "supported_versions": list(self.supported_versions),
            "capabilities": self.capabilities.to_dict(),
            "auth_token": self.auth_token,
        }


@dataclass(frozen=True, slots=True)
class WelcomePayload:
    session_id: str
    selected_version: str
    heartbeat_interval_seconds: int
    max_json_message_bytes: int

    @classmethod
    def from_dict(cls, value: object) -> WelcomePayload:
        data = _object(value, "welcome payload")
        selected_version = _string(data.get("selected_version"), "welcome.selected_version")
        ensure_compatible_version(selected_version)
        return cls(
            session_id=_string(data.get("session_id"), "welcome.session_id"),
            selected_version=selected_version,
            heartbeat_interval_seconds=_integer(
                data.get("heartbeat_interval_seconds"),
                "welcome.heartbeat_interval_seconds",
                minimum=1,
                maximum=60,
            ),
            max_json_message_bytes=_integer(
                data.get("max_json_message_bytes"),
                "welcome.max_json_message_bytes",
                minimum=1024,
                maximum=MAX_JSON_MESSAGE_BYTES,
            ),
        )

    def to_dict(self) -> JsonObject:
        return {
            "session_id": self.session_id,
            "selected_version": self.selected_version,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "max_json_message_bytes": self.max_json_message_bytes,
        }


@dataclass(frozen=True, slots=True)
class StateSnapshotPayload:
    generated_at: str
    state: DisplayState

    @classmethod
    def from_dict(cls, value: object) -> StateSnapshotPayload:
        data = _object(value, "state_snapshot payload")
        return cls(
            generated_at=_timestamp(data.get("generated_at"), "state_snapshot.generated_at"),
            state=DisplayState.from_dict(data.get("state")),
        )

    def to_dict(self) -> JsonObject:
        return {"generated_at": self.generated_at, "state": self.state.to_dict()}


@dataclass(frozen=True, slots=True)
class StatePatchPayload:
    base_sequence: int
    changes: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: object) -> StatePatchPayload:
        data = _object(value, "state_patch payload")
        changes = _object(data.get("changes"), "state_patch.changes")
        unknown = set(changes).difference({"media", "system", "network", "weather", "clock"})
        if unknown:
            raise ValueError(f"state_patch.changes contains unknown sections: {sorted(unknown)}")
        return cls(
            base_sequence=_integer(
                data.get("base_sequence"), "state_patch.base_sequence", minimum=0
            ),
            changes=_json_value(changes, "state_patch.changes"),
        )

    def to_dict(self) -> JsonObject:
        return {"base_sequence": self.base_sequence, "changes": dict(self.changes)}


@dataclass(frozen=True, slots=True)
class CommandPayload:
    command_id: str
    action: CommandAction
    value: float | str | None = None

    @classmethod
    def from_dict(cls, value: object) -> CommandPayload:
        data = _object(value, "command payload")
        try:
            action = CommandAction(_string(data.get("action"), "command.action"))
        except ValueError as exc:
            raise ValueError("command.action is unsupported") from exc
        raw_value = data.get("value")
        if action in {CommandAction.SET_VOLUME, CommandAction.SET_BRIGHTNESS}:
            parsed_value: float | str | None = _number(
                raw_value, "command.value", minimum=0.0, maximum=100.0
            )
        elif action is CommandAction.NAVIGATE:
            parsed_value = _string(raw_value, "command.value")
        elif raw_value is not None:
            raise ValueError(f"command.value must be null for {action.value}")
        else:
            parsed_value = None
        return cls(
            command_id=_string(data.get("command_id"), "command.command_id"),
            action=action,
            value=parsed_value,
        )

    def to_dict(self) -> JsonObject:
        return {
            "command_id": self.command_id,
            "action": self.action.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class CommandResultPayload:
    command_id: str
    success: bool
    error_code: str | None = None
    message: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> CommandResultPayload:
        data = _object(value, "command_result payload")
        success = _boolean(data.get("success"), "command_result.success")
        error_code = _optional_string(data.get("error_code"), "command_result.error_code")
        if success and error_code is not None:
            raise ValueError("successful command_result cannot contain error_code")
        if not success and error_code is None:
            raise ValueError("failed command_result requires error_code")
        return cls(
            command_id=_string(data.get("command_id"), "command_result.command_id"),
            success=success,
            error_code=error_code,
            message=_optional_string(data.get("message"), "command_result.message"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "command_id": self.command_id,
            "success": self.success,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class PingPayload:
    nonce: str

    @classmethod
    def from_dict(cls, value: object) -> PingPayload:
        data = _object(value, "ping payload")
        return cls(nonce=_string(data.get("nonce"), "ping.nonce"))

    def to_dict(self) -> JsonObject:
        return {"nonce": self.nonce}


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    code: str
    message: str
    retryable: bool

    @classmethod
    def from_dict(cls, value: object) -> ErrorPayload:
        data = _object(value, "error payload")
        return cls(
            code=_string(data.get("code"), "error.code"),
            message=_string(data.get("message"), "error.message"),
            retryable=_boolean(data.get("retryable"), "error.retryable"),
        )

    def to_dict(self) -> JsonObject:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


@dataclass(frozen=True, slots=True)
class AssetManifestPayload:
    assets: tuple[AssetMetadata, ...]

    @classmethod
    def from_dict(cls, value: object) -> AssetManifestPayload:
        data = _object(value, "asset_manifest payload")
        raw_assets = data.get("assets")
        if not isinstance(raw_assets, list):
            raise ValueError("asset_manifest.assets must be a list")
        return cls(assets=tuple(AssetMetadata.from_dict(asset) for asset in raw_assets))

    def to_dict(self) -> JsonObject:
        return {"assets": [asset.to_dict() for asset in self.assets]}


Payload: TypeAlias = (
    HelloPayload
    | WelcomePayload
    | StateSnapshotPayload
    | StatePatchPayload
    | FFTFrame
    | CommandPayload
    | CommandResultPayload
    | PingPayload
    | ErrorPayload
    | AssetManifestPayload
)


@dataclass(frozen=True, slots=True)
class Envelope:
    protocol_version: str
    type: MessageType
    message_id: str
    sent_at: str
    sequence: int
    payload: Payload


@dataclass(frozen=True, slots=True)
class AssetFrame:
    metadata: AssetMetadata
    data: bytes


_PAYLOAD_TYPES: dict[MessageType, type[Any]] = {
    MessageType.HELLO: HelloPayload,
    MessageType.WELCOME: WelcomePayload,
    MessageType.STATE_SNAPSHOT: StateSnapshotPayload,
    MessageType.STATE_PATCH: StatePatchPayload,
    MessageType.FFT_FRAME: FFTFrame,
    MessageType.COMMAND: CommandPayload,
    MessageType.COMMAND_RESULT: CommandResultPayload,
    MessageType.PING: PingPayload,
    MessageType.PONG: PingPayload,
    MessageType.ERROR: ErrorPayload,
    MessageType.ASSET_MANIFEST: AssetManifestPayload,
}


def _version_major(version: str) -> int:
    try:
        major, minor = version.split(".", maxsplit=1)
        if not major.isdigit() or not minor.isdigit():
            raise ValueError
        return int(major)
    except ValueError as exc:
        raise ProtocolError("INVALID_VERSION", f"invalid protocol version {version!r}") from exc


def ensure_compatible_version(version: str) -> None:
    """Reject unsupported major versions while allowing additive minor versions."""

    if _version_major(version) != _version_major(PROTOCOL_VERSION):
        raise ProtocolError(
            "UNSUPPORTED_VERSION",
            f"protocol {version} is incompatible with supported version {PROTOCOL_VERSION}",
        )


def negotiate_version(peer_versions: tuple[str, ...]) -> str:
    """Select the local version when the peer supports its major version."""

    if not peer_versions:
        raise ProtocolError("UNSUPPORTED_VERSION", "peer did not advertise protocol versions")
    for version in peer_versions:
        try:
            if _version_major(version) == _version_major(PROTOCOL_VERSION):
                return PROTOCOL_VERSION
        except ProtocolError:
            continue
    raise ProtocolError(
        "UNSUPPORTED_VERSION",
        f"peer versions {peer_versions!r} are incompatible with {PROTOCOL_VERSION}",
    )


def _payload_to_dict(payload: Payload) -> JsonObject:
    return payload.to_dict()


def _payload_from_dict(message_type: MessageType, value: object) -> Payload:
    try:
        if message_type is MessageType.HELLO:
            return HelloPayload.from_dict(value)
        if message_type is MessageType.WELCOME:
            return WelcomePayload.from_dict(value)
        if message_type is MessageType.STATE_SNAPSHOT:
            return StateSnapshotPayload.from_dict(value)
        if message_type is MessageType.STATE_PATCH:
            return StatePatchPayload.from_dict(value)
        if message_type is MessageType.FFT_FRAME:
            return FFTFrame.from_dict(value)
        if message_type is MessageType.COMMAND:
            return CommandPayload.from_dict(value)
        if message_type is MessageType.COMMAND_RESULT:
            return CommandResultPayload.from_dict(value)
        if message_type in {MessageType.PING, MessageType.PONG}:
            return PingPayload.from_dict(value)
        if message_type is MessageType.ERROR:
            return ErrorPayload.from_dict(value)
        if message_type is MessageType.ASSET_MANIFEST:
            return AssetManifestPayload.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("INVALID_PAYLOAD", str(exc)) from exc
    raise ProtocolError("INVALID_PAYLOAD", f"unsupported message type {message_type}")


def new_envelope(
    message_type: MessageType,
    payload: Payload,
    *,
    sequence: int,
    message_id: str | None = None,
    sent_at: str | None = None,
) -> Envelope:
    """Create and validate an outbound envelope."""

    envelope = Envelope(
        protocol_version=PROTOCOL_VERSION,
        type=message_type,
        message_id=message_id or str(uuid.uuid4()),
        sent_at=sent_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        sequence=sequence,
        payload=payload,
    )
    _validate_envelope(envelope)
    return envelope


def _validate_envelope(envelope: Envelope) -> None:
    ensure_compatible_version(envelope.protocol_version)
    _string(envelope.message_id, "message_id")
    _timestamp(envelope.sent_at, "sent_at")
    _integer(envelope.sequence, "sequence")
    expected_payload_type = _PAYLOAD_TYPES[envelope.type]
    if not isinstance(envelope.payload, expected_payload_type):
        raise ProtocolError(
            "PAYLOAD_TYPE_MISMATCH",
            f"{envelope.type.value} requires {expected_payload_type.__name__}",
        )
    _payload_from_dict(envelope.type, _payload_to_dict(envelope.payload))


def encode_envelope(envelope: Envelope) -> bytes:
    """Validate and encode one compact UTF-8 JSON WebSocket text frame."""

    _validate_envelope(envelope)
    document = {
        "protocol_version": envelope.protocol_version,
        "type": envelope.type.value,
        "message_id": envelope.message_id,
        "sent_at": envelope.sent_at,
        "sequence": envelope.sequence,
        "payload": _payload_to_dict(envelope.payload),
    }
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("ENCODING_ERROR", str(exc)) from exc
    if len(encoded) > MAX_JSON_MESSAGE_BYTES:
        raise ProtocolError(
            "MESSAGE_TOO_LARGE",
            f"JSON message exceeds {MAX_JSON_MESSAGE_BYTES} bytes",
        )
    return encoded


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant {value}")


def decode_envelope(data: str | bytes) -> Envelope:
    """Decode and validate an untrusted WebSocket text frame."""

    encoded = data.encode("utf-8") if isinstance(data, str) else data
    if len(encoded) > MAX_JSON_MESSAGE_BYTES:
        raise ProtocolError(
            "MESSAGE_TOO_LARGE",
            f"JSON message exceeds {MAX_JSON_MESSAGE_BYTES} bytes",
        )
    try:
        text = encoded.decode("utf-8")
        document = json.loads(text, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError("INVALID_JSON", "message is not valid UTF-8 JSON") from exc

    try:
        root = _object(document, "message")
        version = _string(root.get("protocol_version"), "protocol_version")
        ensure_compatible_version(version)
        try:
            message_type = MessageType(_string(root.get("type"), "type"))
        except ValueError as exc:
            raise ValueError("type is unsupported") from exc
        envelope = Envelope(
            protocol_version=version,
            type=message_type,
            message_id=_string(root.get("message_id"), "message_id"),
            sent_at=_timestamp(root.get("sent_at"), "sent_at"),
            sequence=_integer(root.get("sequence"), "sequence"),
            payload=_payload_from_dict(message_type, root.get("payload")),
        )
        _validate_envelope(envelope)
        return envelope
    except ProtocolError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("INVALID_ENVELOPE", str(exc)) from exc


_ASSET_PREFIX = struct.Struct(">4sBI")


def encode_asset_frame(metadata: AssetMetadata, data: bytes) -> bytes:
    """Encode one authenticated-by-hash binary album-art frame."""

    try:
        metadata = AssetMetadata.from_dict(metadata.to_dict())
    except ValueError as exc:
        raise ProtocolError("INVALID_ASSET_METADATA", str(exc)) from exc
    if len(data) > MAX_ASSET_BYTES:
        raise ProtocolError("ASSET_TOO_LARGE", f"asset exceeds {MAX_ASSET_BYTES} bytes")
    if metadata.byte_length != len(data):
        raise ProtocolError("ASSET_LENGTH_MISMATCH", "asset length does not match metadata")
    digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(metadata.sha256, digest):
        raise ProtocolError("ASSET_HASH_MISMATCH", "asset SHA-256 does not match metadata")
    header = json.dumps(metadata.to_dict(), separators=(",", ":")).encode("utf-8")
    return _ASSET_PREFIX.pack(ASSET_FRAME_MAGIC, ASSET_FRAME_VERSION, len(header)) + header + data


def decode_asset_frame(frame: bytes) -> AssetFrame:
    """Validate and decode one binary album-art frame."""

    if len(frame) < _ASSET_PREFIX.size:
        raise ProtocolError("INVALID_ASSET_FRAME", "asset frame is truncated")
    magic, version, header_length = _ASSET_PREFIX.unpack_from(frame)
    if magic != ASSET_FRAME_MAGIC:
        raise ProtocolError("INVALID_ASSET_FRAME", "asset frame magic is invalid")
    if version != ASSET_FRAME_VERSION:
        raise ProtocolError("UNSUPPORTED_ASSET_VERSION", f"unsupported asset version {version}")
    header_end = _ASSET_PREFIX.size + header_length
    if header_length > MAX_JSON_MESSAGE_BYTES or header_end > len(frame):
        raise ProtocolError("INVALID_ASSET_FRAME", "asset metadata header is invalid")
    try:
        header = json.loads(frame[_ASSET_PREFIX.size : header_end].decode("utf-8"))
        metadata = AssetMetadata.from_dict(header)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError("INVALID_ASSET_METADATA", str(exc)) from exc
    data = frame[header_end:]
    if len(data) > MAX_ASSET_BYTES:
        raise ProtocolError("ASSET_TOO_LARGE", f"asset exceeds {MAX_ASSET_BYTES} bytes")
    if metadata.byte_length != len(data):
        raise ProtocolError("ASSET_LENGTH_MISMATCH", "asset length does not match metadata")
    digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(metadata.sha256, digest):
        raise ProtocolError("ASSET_HASH_MISMATCH", "asset SHA-256 does not match metadata")
    return AssetFrame(metadata=metadata, data=data)
