# Protocol outline

This is the approved wire-contract outline, not an implemented codec or network service.

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

Unknown optional fields are ignored. Required fields, enums, ranges, payload sizes, and
message sizes will be validated before dispatch. Tokens are never included in normal
messages or logs.

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

## Binary assets

Album art will use a separately specified, versioned binary WebSocket frame containing a
small metadata header and compressed display-ready WebP/JPEG bytes. Assets are hashed,
sent only on change, bounded by size, and stored in a small Pi LRU cache. The exact binary
header is intentionally deferred to the contract milestone.

## Cadence

- FFT: 64 bins at 20–30 FPS, latest value only.
- System/network telemetry: 2–5 Hz.
- Playback: event-driven plus about 1 Hz synchronization.
- Clock and weather: host-controlled periodic updates.
- Heartbeat: every several seconds with explicit stale/offline behavior.
