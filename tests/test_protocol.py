"""Shared wire-contract compatibility and rejection tests."""

from __future__ import annotations

import hashlib
import json

import pytest

from shared.constants import MAX_JSON_MESSAGE_BYTES, PROTOCOL_VERSION, CommandAction, MessageType
from shared.models import (
    AssetMetadata,
    ClockState,
    DisplayCapabilities,
    DisplayState,
    FFTFrame,
    GpuMetrics,
    MediaState,
    NetworkMetrics,
    SystemMetrics,
    WeatherState,
)
from shared.protocol import (
    AssetManifestPayload,
    CommandPayload,
    CommandResultPayload,
    ErrorPayload,
    HelloPayload,
    PingPayload,
    ProtocolError,
    StatePatchPayload,
    StateSnapshotPayload,
    WelcomePayload,
    decode_asset_frame,
    decode_envelope,
    encode_asset_frame,
    encode_envelope,
    ensure_compatible_version,
    negotiate_version,
    new_envelope,
)

NOW = "2026-07-22T15:30:00Z"


def capabilities() -> DisplayCapabilities:
    return DisplayCapabilities(
        width=480,
        height=320,
        orientation=90,
        target_fps=25,
        touch_enabled=False,
    )


def sample_state() -> DisplayState:
    return DisplayState(
        media=MediaState(
            title="After Dark",
            artist="Mr.Kitty",
            album=None,
            is_playing=True,
            position_seconds=43.0,
            duration_seconds=251.0,
            volume_percent=65.0,
        ),
        system=SystemMetrics(
            cpu_usage_percent=22.0,
            gpu_usage_percent=71.0,
            ram_usage_percent=38.5,
            cpu_temperature_c=54.0,
            gpu_temperature_c=63.0,
            gpus=(
                GpuMetrics(name="Intel GPU", usage_percent=12.0),
                GpuMetrics(name="NVIDIA GPU", usage_percent=71.0),
            ),
        ),
        network=NetworkMetrics(
            download_bytes_per_second=125_000.0,
            upload_bytes_per_second=12_500.0,
        ),
        weather=WeatherState(
            temperature_c=24.0,
            condition="Clear",
            observed_at=NOW,
        ),
        clock=ClockState(time_text="17:00:00", date_text="Wednesday 29 July"),
    )


@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        (
            MessageType.HELLO,
            HelloPayload(
                client_id="display-pi",
                supported_versions=(PROTOCOL_VERSION,),
                capabilities=capabilities(),
                auth_token="secret-not-in-repr",
            ),
        ),
        (
            MessageType.WELCOME,
            WelcomePayload(
                session_id="session-1",
                selected_version=PROTOCOL_VERSION,
                heartbeat_interval_seconds=5,
                max_json_message_bytes=MAX_JSON_MESSAGE_BYTES,
            ),
        ),
        (
            MessageType.STATE_SNAPSHOT,
            StateSnapshotPayload(generated_at=NOW, state=sample_state()),
        ),
        (
            MessageType.STATE_PATCH,
            StatePatchPayload(base_sequence=4, changes={"system": {"cpu_usage_percent": 42.0}}),
        ),
        (
            MessageType.FFT_FRAME,
            FFTFrame(captured_at=NOW, bins=(0.25,) * 64),
        ),
        (
            MessageType.COMMAND,
            CommandPayload(
                command_id="command-1",
                action=CommandAction.SET_VOLUME,
                value=55.0,
            ),
        ),
        (
            MessageType.COMMAND_RESULT,
            CommandResultPayload(command_id="command-1", success=True),
        ),
        (MessageType.PING, PingPayload(nonce="ping-1")),
        (MessageType.PONG, PingPayload(nonce="ping-1")),
        (
            MessageType.ERROR,
            ErrorPayload(code="SOURCE_UNAVAILABLE", message="Spotify unavailable", retryable=True),
        ),
        (MessageType.ASSET_MANIFEST, AssetManifestPayload(assets=())),
    ],
)
def test_json_message_round_trip(message_type: MessageType, payload: object) -> None:
    envelope = new_envelope(
        message_type,
        payload,  # type: ignore[arg-type]
        sequence=7,
        sent_at=NOW,
    )
    decoded = decode_envelope(encode_envelope(envelope))
    assert decoded == envelope


def test_unknown_optional_fields_are_ignored() -> None:
    envelope = new_envelope(
        MessageType.PING,
        PingPayload(nonce="ping-1"),
        sequence=1,
        sent_at=NOW,
    )
    document = json.loads(encode_envelope(envelope))
    document["future_envelope_field"] = True
    document["payload"]["future_payload_field"] = "safe"
    assert decode_envelope(json.dumps(document)).payload == PingPayload(nonce="ping-1")


def test_auth_token_is_redacted_from_repr() -> None:
    payload = HelloPayload(
        client_id="display-pi",
        supported_versions=(PROTOCOL_VERSION,),
        capabilities=capabilities(),
        auth_token="super-secret",
    )
    assert "super-secret" not in repr(payload)


def test_rejects_incompatible_major_version() -> None:
    with pytest.raises(ProtocolError) as error:
        ensure_compatible_version("2.0")
    assert error.value.code == "UNSUPPORTED_VERSION"


def test_negotiates_supported_major_version() -> None:
    assert negotiate_version(("2.0", "1.2")) == PROTOCOL_VERSION


@pytest.mark.parametrize(
    "data",
    [
        b"not-json",
        b"[]",
        b'{"protocol_version":"1.0"}',
        b'{"protocol_version":"1.0","type":"unknown"}',
        b'{"protocol_version":"1.0","type":"ping","sequence":-1}',
    ],
)
def test_rejects_malformed_envelopes(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_envelope(data)


def test_rejects_oversized_json_before_parsing() -> None:
    with pytest.raises(ProtocolError) as error:
        decode_envelope(b" " * (MAX_JSON_MESSAGE_BYTES + 1))
    assert error.value.code == "MESSAGE_TOO_LARGE"


def test_rejects_invalid_fft_frame() -> None:
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "type": "fft_frame",
        "message_id": "message-1",
        "sent_at": NOW,
        "sequence": 1,
        "payload": {"captured_at": NOW, "bins": [0.5] * 63},
    }
    with pytest.raises(ProtocolError, match="exactly 64"):
        decode_envelope(json.dumps(envelope))


def test_rejects_invalid_outbound_payload() -> None:
    invalid = FFTFrame(captured_at=NOW, bins=(0.5,) * 63)
    with pytest.raises(ProtocolError, match="exactly 64"):
        new_envelope(MessageType.FFT_FRAME, invalid, sequence=1, sent_at=NOW)


def test_asset_frame_round_trip_and_tamper_detection() -> None:
    data = b"small-webp-payload"
    metadata = AssetMetadata(
        asset_id="album-art-1",
        sha256=hashlib.sha256(data).hexdigest(),
        media_type="image/webp",
        byte_length=len(data),
    )
    encoded = encode_asset_frame(metadata, data)
    assert decode_asset_frame(encoded).data == data

    tampered = encoded[:-1] + bytes([encoded[-1] ^ 0xFF])
    with pytest.raises(ProtocolError) as error:
        decode_asset_frame(tampered)
    assert error.value.code == "ASSET_HASH_MISMATCH"


def test_rgb565_asset_metadata_requires_dimensions() -> None:
    data = b"\x00\xf8" * 4
    metadata = AssetMetadata(
        asset_id="album-rgb565",
        sha256=hashlib.sha256(data).hexdigest(),
        media_type="image/rgb565",
        byte_length=len(data),
        width=2,
        height=2,
    )
    encoded = encode_asset_frame(metadata, data)
    decoded = decode_asset_frame(encoded)
    assert decoded.metadata.width == 2
    assert decoded.metadata.height == 2
    assert decoded.metadata.media_type == "image/rgb565"

    with pytest.raises(ValueError, match="require width and height"):
        AssetMetadata.from_dict(
            {
                "asset_id": "bad",
                "sha256": hashlib.sha256(data).hexdigest(),
                "media_type": "image/rgb565",
                "byte_length": len(data),
            }
        )


def test_rejects_invalid_metric_percentage() -> None:
    with pytest.raises(ValueError, match="must not exceed 100"):
        SystemMetrics.from_dict({"cpu_usage_percent": 101})
