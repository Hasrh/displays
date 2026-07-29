# Architecture

## Status and scope

The approved design is host-authoritative and event-driven. This milestone implements
package boundaries, typed configuration, protocol vocabulary, and hardware discovery only.
It does not implement networking, collection, rendering, touch handling, or commands.

## Topology

- **Windows host:** one `asyncio` composition root owns collectors, canonical state,
  audio/FFT processing, asset preparation, command execution, and the WebSocket server.
  Blocking system and HTTP sampling runs in a worker thread so it cannot stall transport.
- **Raspberry Pi:** one future foreground process managed by `systemd` reconnects to the
  host, keeps the latest immutable state and a bounded asset cache, renders at a fixed rate,
  and translates input into semantic actions.
- **Shared:** dependency-light dataclasses, limits, enums, and explicit validation/codecs.
  Shared code must remain portable to Python 3.11 on both systems.

Windows is authoritative for media, sensors, weather, clock synchronization, FFT, image
preprocessing, and host commands. The Pi may interpolate animation, cache prepared assets,
render, adjust local brightness, and forward controls.

## Runtime rules

- A single long-lived WebSocket carries JSON envelopes and versioned binary asset frames.
  Its primary TCP transport is the private Wi-Fi LAN; the direct USB Ethernet gadget remains
  an optional deployment profile because transport details do not leak into application code.
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
- Display and touch drivers remain behind interfaces. The verified fbtft overlay exposes
  480×320 logical coordinates after its 90-degree rotation; future touch calibration occurs
  once at the hardware boundary.

The implemented renderer uses the verified 480×320 framebuffer geometry, an allocation-
conscious RGB565 canvas, frame-rate-independent FFT smoothing, and a fixed-rate render loop.
It consumes immutable snapshots and only the newest FFT frame. Now Playing, Visualizer,
System, and Clock/Weather implementations use the same `Page` contract. `PageManager` owns
selection, wrapping, automatic cycling, transition revisions, and page indicators; future
touch gestures only emit navigation actions to that manager.

## Delivery gates

1. Architecture approval.
2. This scaffolding and read-only hardware discovery foundation.
3. Shared contracts and compatibility tests.
4. WebSocket handshake, heartbeat, snapshots, reconnect, and synthetic data.
5. Headless renderer, then real display integration after hardware identification.
6. Pages/navigation; calibrated touch remains deferred.
7. Real Windows CPU, RAM, network, and optional LibreHardwareMonitor GPU collectors.
8. Album art, FFT, and on-device performance tuning.

The LCDWiki MPI3501 display path is verified: ILI9486 via fbtft, the
`tft35a:rotate=90` overlay, and a 480×320 RGB565 framebuffer at `/dev/fb1`.
Touch remains intentionally deferred. Sustained framebuffer throughput still needs
measurement on the Pi Zero W before selecting the production frame rate.
