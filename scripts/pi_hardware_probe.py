#!/usr/bin/env python3
"""Read-only Raspberry Pi display/touch hardware inventory.

The probe reads procfs, sysfs, device-tree, and boot configuration. It never writes files,
loads modules, changes overlays, opens input devices, or changes system configuration.
Run it on the Raspberry Pi, not the Windows development host.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

Report = dict[str, Any]


def read_text(path: Path, *, binary_nul_separator: bool = False) -> str | None:
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return None
    if binary_nul_separator:
        data = data.replace(b"\x00", b", ")
    return data.decode("utf-8", errors="replace").strip(" \t\r\n\x00")


def existing_paths(patterns: Iterable[str]) -> list[str]:
    results: list[str] = []
    for pattern in patterns:
        try:
            results.extend(str(path) for path in sorted(Path("/").glob(pattern.lstrip("/"))))
        except OSError:
            continue
    return sorted(set(results))


def probe_system() -> Report:
    os_release = read_text(Path("/etc/os-release"))
    model = read_text(Path("/proc/device-tree/model"), binary_nul_separator=True)
    return {
        "platform": platform.platform(),
        "kernel": platform.uname()._asdict(),
        "python": sys.version.split()[0],
        "os_release": os_release or "unavailable",
        "device_tree_model": model or "unavailable",
    }


def probe_device_tree() -> Report:
    base = Path("/proc/device-tree")
    compatible = read_text(base / "compatible", binary_nul_separator=True)
    overlay_paths = existing_paths(
        (
            "/proc/device-tree/chosen/overlays/*",
            "/sys/kernel/config/device-tree/overlays/*",
        )
    )
    overlays: Report = {}
    for raw_path in overlay_paths:
        path = Path(raw_path)
        overlays[raw_path] = {
            child.name: read_text(child, binary_nul_separator=True) or "<binary/empty>"
            for child in sorted(path.iterdir())
            if child.is_file()
        }

    boot_configs: Report = {}
    for path in (Path("/boot/firmware/config.txt"), Path("/boot/config.txt")):
        content = read_text(path)
        if content is not None:
            relevant = [
                line.strip()
                for line in content.splitlines()
                if line.strip().lower().startswith(("dtoverlay", "dtparam=spi", "display_"))
            ]
            boot_configs[str(path)] = relevant

    return {
        "compatible": compatible or "unavailable",
        "overlay_nodes": overlays,
        "relevant_boot_config_lines": boot_configs,
    }


def probe_display() -> Report:
    framebuffers: Report = {}
    for raw_path in existing_paths(("/sys/class/graphics/fb*",)):
        path = Path(raw_path)
        framebuffers[path.name] = {
            "name": read_text(path / "name") or "unavailable",
            "modes": read_text(path / "modes") or "unavailable",
            "virtual_size": read_text(path / "virtual_size") or "unavailable",
            "device": str((path / "device").resolve(strict=False)),
        }

    drm: Report = {}
    for raw_path in existing_paths(("/sys/class/drm/card*",)):
        path = Path(raw_path)
        if "-" in path.name:
            continue
        device = path / "device"
        drm[path.name] = {
            "driver": str((device / "driver").resolve(strict=False)),
            "modalias": read_text(device / "modalias") or "unavailable",
            "connectors": existing_paths((f"/sys/class/drm/{path.name}-*",)),
        }

    return {
        "device_nodes": existing_paths(("/dev/fb*", "/dev/dri/*")),
        "framebuffers": framebuffers,
        "drm_cards": drm,
    }


def probe_spi() -> Report:
    devices: Report = {}
    for raw_path in existing_paths(("/sys/bus/spi/devices/*",)):
        path = Path(raw_path)
        devices[path.name] = {
            "modalias": read_text(path / "modalias") or "unavailable",
            "driver": str((path / "driver").resolve(strict=False)),
            "of_node": str((path / "of_node").resolve(strict=False)),
        }

    module_text = read_text(Path("/proc/modules")) or ""
    interesting_terms = (
        "spi",
        "ili",
        "fbtft",
        "tinydrm",
        "panel",
        "ads7846",
        "xpt2046",
        "touch",
    )
    modules = [
        line
        for line in module_text.splitlines()
        if any(term in line.lower() for term in interesting_terms)
    ]
    return {
        "device_nodes": existing_paths(("/dev/spidev*",)),
        "sysfs_devices": devices,
        "relevant_loaded_modules": modules,
    }


def parse_input_blocks(content: str) -> list[Report]:
    devices: list[Report] = []
    for block in content.strip().split("\n\n"):
        if not block.strip():
            continue
        fields: Report = {}
        for line in block.splitlines():
            if len(line) > 3 and line[1:3] == ": ":
                fields.setdefault(line[0], []).append(line[3:])
        devices.append(fields)
    return devices


def probe_input() -> Report:
    proc_content = read_text(Path("/proc/bus/input/devices"))
    capabilities: Report = {}
    for raw_path in existing_paths(("/sys/class/input/event*/device",)):
        path = Path(raw_path)
        capability_dir = path / "capabilities"
        capabilities[path.parent.name] = {
            "name": read_text(path / "name") or "unavailable",
            "phys": read_text(path / "phys") or "unavailable",
            "properties": read_text(path / "properties") or "unavailable",
            "capabilities": {
                name: read_text(capability_dir / name) or "unavailable"
                for name in ("abs", "ev", "key", "rel", "sw")
            },
        }
    return {
        "device_nodes": existing_paths(("/dev/input/event*",)),
        "proc_devices": parse_input_blocks(proc_content) if proc_content else "unavailable",
        "sysfs_capabilities_hex": capabilities,
    }


def collect_report() -> Report:
    return {
        "warning": (
            "Read-only inventory only. Verify wiring and device paths before selecting an overlay."
        ),
        "system": probe_system(),
        "device_tree": probe_device_tree(),
        "display": probe_display(),
        "spi": probe_spi(),
        "input": probe_input(),
    }


def render_human(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(render_human(child, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {child}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}(none found)"]
        lines = []
        for child in value:
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(render_human(child, indent + 1))
            else:
                lines.append(f"{prefix}- {child}")
        return lines
    return [f"{prefix}{value}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = collect_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("\n".join(render_human(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
