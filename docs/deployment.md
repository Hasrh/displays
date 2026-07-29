# Deployment outline

Deployment is intentionally not active at this milestone.

The default data path is the private Wi-Fi LAN. Reserve the Windows host address in the
router so the Pi endpoint remains stable. Direct USB Ethernet remains an optional deployment
profile documented in `docs/usb-direct.md`.

## Windows development host

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item config\host.example.toml config\host.toml
.\.venv\Scripts\python -m pc.main --config config\host.toml
```

Set the same token on Windows and the Pi. It must contain at least 16 characters:

```powershell
$env:DESKTOP_DISPLAY_TOKEN = "replace-with-a-long-random-secret"
python -m pc.main --config config/host.toml
```

The host binds only the configured Wi-Fi address and streams synthetic state until real
collectors are implemented. Permit inbound TCP 8765 on the Windows Private firewall profile.

```powershell
New-NetFirewallRule `
  -DisplayName "Desktop Companion Display WebSocket (Wi-Fi)" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private
```

## Raspberry Pi probe

Copy the repository or just `scripts/pi_hardware_probe.py` to the Pi, then run:

```console
python3 --version
python3 scripts/pi_hardware_probe.py
python3 scripts/pi_hardware_probe.py --json > pi-hardware-probe.json
```

The probe needs no third-party packages and makes no configuration changes. Normal-user
output is preferred; if entries show `unavailable`, rerun with `sudo` only to read protected
inventory and review the script first. Do not enable SPI or apply an overlay merely to make
the report look complete.

## Verified framebuffer test

The LCDWiki MPI3501 is exposed as `/dev/fb1` with 480×320 RGB565 geometry. Copy the example
configuration and run the explicit hardware test:

```console
cp config/pi.example.toml config/pi.toml
python3 -m pi.main --config config/pi.toml --display-test
```

This writes static RGB565 color bars and exits. The test does not configure SPI, load a
driver, contact the Windows host, or access touch input. The user running it must belong to
the `video` group or otherwise have write access to `/dev/fb1`.

## Raspberry Pi network test

```console
export DESKTOP_DISPLAY_TOKEN="replace-with-the-same-long-random-secret"
python3 -m pi.main --config config/pi.toml --network-test
```

The Pi negotiates protocol version 1, authenticates, receives a full snapshot and 64-bin FFT
frames, responds to application heartbeats, and reconnects with exponential backoff and
jitter. This test logs state but does not render it.

## Live dashboard

Start the Windows host as above, then run on the Pi:

```console
export DESKTOP_DISPLAY_TOKEN="replace-with-the-same-long-random-secret"
python3 -m pi.main --config config/pi.toml --run-display
```

The first page combines CPU, GPU, RAM, network throughput, playback progress, connection
status, and smoothed FFT bars. It renders directly into RGB565 and writes full frames to
`/dev/fb1`; network tasks never block the fixed-rate render loop.

Start with `display.target_fps = 10` on the Pi Zero W. Renderer logs report measured FPS and
missed deadlines every five seconds, with separate `render_ms` and `write_ms` averages.
The RGB565 canvas uses NumPy vectorization and cached bitmap text to keep Python work off the
critical path. Increase the rate only after observing stable CPU, temperature, and frame timing
on the physical device.

## Future Pi service

Production deployment will use a dedicated unprivileged service account and a foreground
`systemd` unit with restart backoff. Configuration and authentication material will live
outside the source tree with restrictive permissions. The service will require the `video`
group for the verified framebuffer; input permissions are unnecessary while touch is disabled.

Production installation, service units, firewall rules, TLS/authentication, and dependencies
are deferred until their implementation milestones. Never expose a future unauthenticated
listener or commit a pre-shared token.
