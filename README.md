# Desktop Companion Display

Desktop Companion Display is a host-authoritative companion screen: Windows will collect
and process data, while a Raspberry Pi Zero WH will render cached state and forward input.
This repository contains the approved project scaffolding, configuration parsers, protocol
vocabulary, a read-only Raspberry Pi hardware probe, and an RGB565 framebuffer backend for
hardware testing. Networking, pages, collectors, and command execution are not implemented.

## Requirements

- Python 3.11 or newer
- Windows for the future host runtime
- Raspberry Pi OS for hardware probing and the future renderer

## Development

```console
python -m venv .venv
python -m pip install -e ".[dev]"
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

`python -m pc.main --config config/host.toml` and
`python -m pi.main --config config/pi.toml` validate configuration and then exit clearly
because runtime features have not been implemented. The Pi entry point writes to the
configured framebuffer only when the explicit `--display-test` option is supplied.

The verified LCD path is an LCDWiki MPI3501 using `fb_ili9486`, `/dev/fb1`, 480×320 RGB565,
and `dtoverlay=tft35a:rotate=90`. Touch is intentionally disabled. See `docs/hardware.md`
and `docs/deployment.md` before running the framebuffer test.

## License

Released under the MIT License. See `LICENSE`.
