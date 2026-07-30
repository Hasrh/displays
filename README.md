# Desktop Companion Display

Desktop Companion Display is a host-authoritative companion screen: Windows will collect
and process data, while a Raspberry Pi Zero WH will render cached state and forward input.
This repository contains the approved project scaffolding, configuration parsers, validated
shared protocol contracts, a read-only Raspberry Pi hardware probe, and an RGB565 framebuffer
backend for hardware testing. The authenticated WebSocket host/client and synthetic transport
stream are implemented. A live RGB565 system/FFT dashboard now renders that state on the
verified framebuffer. Now Playing, Visualizer, System, and Clock/Weather pages share a
configurable navigation manager. Windows CPU, RAM, network telemetry, and Global System Media
Transport Controls metadata are live, with per-GPU telemetry from an optional local
LibreHardwareMonitor endpoint. Live WASAPI loopback FFT drives the visualizer when available.
Host-prepared RGB565 album art is transferred and cached on the Pi. Themes (`dark`,
`cyberpunk`, `minimal`, `retro`) and lightweight progress/page animations are configurable.
Weather, touch navigation, and playback command execution are paused.

## Requirements

- Python 3.11 or newer
- Windows for the future host runtime
- Raspberry Pi OS for hardware probing and the future renderer
- `libopenblas0-pthread` on Raspberry Pi OS for the NumPy RGB565 renderer
- LibreHardwareMonitor on Windows for per-GPU load, VRAM, and temperature metrics

## Development

```console
python -m venv .venv
python -m pip install -e ".[host,dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

Copy, do not edit, the examples before local use:

```console
copy config\host.example.toml config\host.toml
cp config/pi.example.toml config/pi.toml
```

No secret is included in either example. Future authentication tokens must be provided
outside source control (preferably through environment variables).

## Entry points

`python -m pc.main --config config/host.toml` starts the authenticated WebSocket host with
real Windows system, media, and WASAPI loopback FFT telemetry plus synthetic fallbacks for
unfinished integrations. The Pi entry point offers `--network-test`, `--display-test`, and
`--run-display`; without a mode it validates configuration without touching hardware.

The verified LCD path is an LCDWiki MPI3501 using `fb_ili9486`, `/dev/fb1`, 480×320 RGB565,
and `dtoverlay=tft35a:rotate=90`. Touch is intentionally disabled. See `docs/hardware.md`
and `docs/deployment.md` before running the framebuffer test.

The default data link is a private Wi-Fi LAN with a router-reserved Windows address. Direct
USB Ethernet remains optional; follow `docs/usb-direct.md` rather than editing boot files
from memory.

## License

Released under the MIT License. See `LICENSE`.
