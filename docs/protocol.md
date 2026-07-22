# Protocol contract

The dependency-free codec and validators are implemented in `shared/protocol.py`; immutable
domain models live in `shared/models.py`. Both endpoints use this exact code before dispatch.
The WebSocket transport itself is the next milestone.

## JSON envelope

Every text message uses:

```json
{
  "protocol_version": "1.0",
  "type": "hello",
  "message_id": "unique-id",
  "sent_at": "RFC-3339 UTC timestamp",
  "sequence": 1,
  "payload": {}
}
```

- `protocol_version`: major/minor version; unsupported major versions fail clearly.
- `type`: one of the agreed message families below.
- `message_id`: unique identifier used for tracing and idempotent command results.
- `sent_at`: UTC capture/send time; local scheduling uses monotonic clocks.
- `sequence`: non-negative per-session ordering value.
- `payload`: type-specific JSON object.

Unknown optional fields are ignored. Required fields, enums, ranges, finite numeric values,
payload shapes, and the 256 KiB JSON limit are validated before dispatch. Unsupported major
versions are rejected; additive minor versions remain compatible. Authentication tokens are
redacted from dataclass representations and must never be logged.

## Message families

- `hello` / `welcome`: negotiate version, display dimensions/orientation, capabilities,
  desired rates, theme, and authentication.
- `state_snapshot`: complete authoritative state sent at handshake/reconnect.
- `state_patch`: validated changes relative to the latest snapshot.
- `fft_frame`: capture timestamp plus 64 normalized bins; only the newest pending frame
  survives.
- `command` / `command_result`: unique command ID and explicit success/failure result.
  Retries must be idempotent. Brightness is Pi-local; media and volume are host commands.
- `ping` / `pong`: liveness and latency measurement.
- `error`: machine-readable code plus safe diagnostic text.
- `asset_manifest`: current prepared assets and hashes.

Concrete payload dataclasses include `HelloPayload`, `WelcomePayload`,
`StateSnapshotPayload`, `StatePatchPayload`, `FFTFrame`, `CommandPayload`,
`CommandResultPayload`, `PingPayload`, `ErrorPayload`, and `AssetManifestPayload`.
Display state is composed from typed media, system, network, and weather models.

## Binary assets

Album art uses a versioned binary WebSocket frame:

1. Four-byte magic: `DDAS`
2. One-byte frame version: `1`
3. Four-byte big-endian JSON metadata-header length
4. UTF-8 JSON `AssetMetadata`
5. JPEG or WebP bytes

The metadata contains `asset_id`, lowercase SHA-256, MIME type, and byte length. Encoding
and decoding verify the declared length, 2 MiB limit, media type, frame version, and SHA-256
using constant-time digest comparison. Assets are sent only on hash change and will be stored
in a small Pi LRU cache.

## Cadence

- FFT: 64 bins at 20–30 FPS, latest value only.
- System/network telemetry: 2–5 Hz.
- Playback: event-driven plus about 1 Hz synchronization.
- Clock and weather: host-controlled periodic updates.
- Heartbeat: every several seconds with explicit stale/offline behavior.
