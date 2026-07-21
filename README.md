# Desktop Companion Display

Desktop Companion Display is a host-authoritative companion screen: Windows will collect
and process data, while a Raspberry Pi Zero WH will render cached state and forward input.
This repository currently contains only the approved project scaffolding, configuration
parsers, protocol vocabulary, and a read-only Raspberry Pi hardware probe. Networking,
collectors, rendering, and command execution are intentionally not implemented.

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
because runtime features have not been implemented. They never start a listener or alter
hardware.

Run `python scripts/pi_hardware_probe.py` on the Raspberry Pi and share its output before
selecting display or touch drivers. The ILI9486 LCD and XPT2046 touch controllers are
identified, but wiring, kernel overlay, device paths, rotation, and calibration still require
probe output and the board pinout. See `docs/hardware.md`.

## License

Released under the MIT License. See `LICENSE`.
