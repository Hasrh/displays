# Architecture

## Status and scope

The approved design is host-authoritative and event-driven. This milestone implements
package boundaries, typed configuration, protocol vocabulary, and hardware discovery only.
It does not implement networking, collection, rendering, touch handling, or commands.

## Topology

- **Windows host:** one future `asyncio` composition root owns collectors, canonical state,
  audio/FFT processing, asset preparation, command execution, and the WebSocket server.
  Blocking adapters will sit behind bounded queues in workers.
- **Raspberry Pi:** one future foreground process managed by `systemd` reconnects to the
  host, keeps the latest immutable state and a bounded asset cache, renders at a fixed rate,
  and translates input into semantic actions.
- **Shared:** dependency-light dataclasses, limits, enums, and explicit validation/codecs.
  Shared code must remain portable to Python 3.11 on both systems.

Windows is authoritative for media, sensors, weather, clock synchronization, FFT, image
preprocessing, and host commands. The Pi may interpolate animation, cache prepared assets,
render, adjust local brightness, and forward controls.

## Runtime rules

- A single long-lived WebSocket will carry JSON envelopes and versioned binary asset frames.
- Latest-value semantics prevent telemetry and FFT backlogs; render work never waits on I/O.
- Reconnect uses exponential backoff with jitter and begins with a full snapshot plus asset
  manifest.
- Monotonic timestamps, bounded queues, cancellation-aware shutdown, message-size limits,
  actionable configuration errors, and token redaction are mandatory.
- Optional collectors degrade independently. Disconnected, stale, degraded, and fatal
  hardware states are distinct.

## Boundaries

- `pc/` contains only host composition, configuration, state, transport, collector, audio,
  command, and asset boundaries.
- `pi/` contains only Pi composition, configuration, state, transport, display, renderer,
  page, navigation, touch, theme, animation, and asset boundaries.
- `shared/` cannot import platform-specific host or Pi modules.
- Pages will receive read-only render context and cannot access networking or hardware.
- Display and touch drivers remain behind interfaces. Logical UI coordinates are 320×480;
  rotation/calibration occur once at the hardware boundary.

## Delivery gates

1. Architecture approval.
2. This scaffolding and read-only hardware discovery foundation.
3. Shared contracts and compatibility tests.
4. WebSocket handshake, heartbeat, snapshots, reconnect, and synthetic data.
5. Headless renderer, then real display integration after hardware identification.
6. Pages/navigation and calibrated touch.
7. Real Windows collectors.
8. Album art, FFT, and on-device performance tuning.

The ILI9486 display and XPT2046 touch controllers are identified. SPI wiring/chip selects,
overlay, rotation, display device, input device, calibration, and throughput must still be
verified before a concrete Pi backend is selected.
