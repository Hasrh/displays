#!/usr/bin/env python3
"""Configure a Raspberry Pi Zero W as a fixed-address USB Ethernet gadget.

This script targets Raspberry Pi OS Bookworm with NetworkManager. It creates a
one-time backup before changing boot files and supports an explicit rollback.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

PI_ADDRESS = "192.168.7.2/24"
CONNECTION_NAME = "desktop-display-usb"
GADGET_OVERLAY = "dtoverlay=dwc2,dr_mode=peripheral"
MODULES = ("dwc2", "g_ether")
HOST_MAC = "02:dd:00:00:00:01"
DEVICE_MAC = "02:dd:00:00:00:02"

BOOT_DIRECTORY = Path("/boot/firmware")
CONFIG_PATH = BOOT_DIRECTORY / "config.txt"
CMDLINE_PATH = BOOT_DIRECTORY / "cmdline.txt"
BACKUP_DIRECTORY = Path("/var/lib/desktop-display/usb-gadget-backup")


class SetupError(RuntimeError):
    """Raised when setup cannot continue safely."""


def update_config_text(text: str) -> str:
    """Replace conflicting dwc2 overlays with one peripheral-mode overlay."""

    lines = text.splitlines()
    output: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("dtoverlay=dwc2"):
            if not replaced:
                output.append(GADGET_OVERLAY)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1]:
            output.append("")
        output.extend(("[all]", GADGET_OVERLAY))
    return "\n".join(output) + "\n"


def update_cmdline_text(text: str) -> str:
    """Add gadget modules and stable MAC addresses to the one-line cmdline."""

    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if len(nonempty) != 1:
        raise SetupError("cmdline.txt must contain exactly one non-empty line")

    tokens = nonempty[0].split()
    modules: list[str] = []
    retained: list[str] = []
    for token in tokens:
        if token.startswith("modules-load="):
            modules.extend(item for item in token.removeprefix("modules-load=").split(",") if item)
        elif not token.startswith(("g_ether.host_addr=", "g_ether.dev_addr=")):
            retained.append(token)

    for module in MODULES:
        if module not in modules:
            modules.append(module)
    retained.extend(
        (
            f"modules-load={','.join(modules)}",
            f"g_ether.host_addr={HOST_MAC}",
            f"g_ether.dev_addr={DEVICE_MAC}",
        )
    )
    return " ".join(retained) + "\n"


def _run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
    )


def _require_supported_system() -> None:
    if platform.system() != "Linux":
        raise SetupError("run this script on the Raspberry Pi, not Windows")
    if not CONFIG_PATH.is_file() or not CMDLINE_PATH.is_file():
        raise SetupError("Raspberry Pi Bookworm boot files were not found under /boot/firmware")
    os_release = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    if "VERSION_CODENAME=bookworm" not in os_release:
        raise SetupError("this script supports Raspberry Pi OS Bookworm only")
    if shutil.which("nmcli") is None:
        raise SetupError("NetworkManager nmcli is required")


def _require_root() -> None:
    get_effective_user_id = getattr(os, "geteuid", None)
    if not callable(get_effective_user_id) or get_effective_user_id() != 0:
        raise SetupError("apply and restore must be run with sudo")


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        delete=False,
    ) as stream:
        stream.write(text)
        temporary = Path(stream.name)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _create_backup() -> None:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for source in (CONFIG_PATH, CMDLINE_PATH):
        destination = BACKUP_DIRECTORY / source.name
        if not destination.exists():
            shutil.copy2(source, destination)


def _connection_exists() -> bool:
    result = _run(
        ("nmcli", "-t", "-f", "NAME", "connection", "show", CONNECTION_NAME),
        check=False,
    )
    return result.returncode == 0


def _configure_network_manager() -> None:
    common = (
        "connection.interface-name",
        "usb0",
        "connection.autoconnect",
        "yes",
        "ipv4.method",
        "manual",
        "ipv4.addresses",
        PI_ADDRESS,
        "ipv4.never-default",
        "yes",
        "ipv6.method",
        "disabled",
    )
    if _connection_exists():
        _run(("nmcli", "connection", "modify", CONNECTION_NAME, *common))
    else:
        _run(
            (
                "nmcli",
                "connection",
                "add",
                "type",
                "ethernet",
                "ifname",
                "usb0",
                "con-name",
                CONNECTION_NAME,
                *common,
            )
        )


def apply() -> None:
    _require_supported_system()
    _require_root()
    original_config = CONFIG_PATH.read_text(encoding="utf-8")
    original_cmdline = CMDLINE_PATH.read_text(encoding="utf-8")
    updated_config = update_config_text(original_config)
    updated_cmdline = update_cmdline_text(original_cmdline)

    _configure_network_manager()
    _create_backup()
    try:
        _atomic_write(CONFIG_PATH, updated_config)
        _atomic_write(CMDLINE_PATH, updated_cmdline)
    except OSError:
        shutil.copy2(BACKUP_DIRECTORY / CONFIG_PATH.name, CONFIG_PATH)
        shutil.copy2(BACKUP_DIRECTORY / CMDLINE_PATH.name, CMDLINE_PATH)
        raise

    print("USB gadget configuration applied.")
    print(f"Pi USB address: {PI_ADDRESS}")
    print("Reboot is required. Keep Wi-Fi available until the USB link is verified.")


def restore() -> None:
    _require_supported_system()
    _require_root()
    config_backup = BACKUP_DIRECTORY / CONFIG_PATH.name
    cmdline_backup = BACKUP_DIRECTORY / CMDLINE_PATH.name
    if not config_backup.is_file() or not cmdline_backup.is_file():
        raise SetupError(f"backup not found at {BACKUP_DIRECTORY}")
    shutil.copy2(config_backup, CONFIG_PATH)
    shutil.copy2(cmdline_backup, CMDLINE_PATH)
    if _connection_exists():
        _run(("nmcli", "connection", "delete", CONNECTION_NAME))
    print("Original boot configuration restored. Reboot is required.")


def check() -> None:
    _require_supported_system()
    config = CONFIG_PATH.read_text(encoding="utf-8")
    cmdline = CMDLINE_PATH.read_text(encoding="utf-8")
    print(f"peripheral overlay: {GADGET_OVERLAY in config}")
    print(f"gadget modules: {all(module in cmdline for module in MODULES)}")
    print(f"stable gadget MACs: {HOST_MAC in cmdline and DEVICE_MAC in cmdline}")
    print(f"NetworkManager profile: {_connection_exists()}")
    interface = _run(("ip", "-brief", "-4", "address", "show", "usb0"), check=False)
    print(f"usb0: {interface.stdout.strip() or 'not present (connect cable after reboot)'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--apply", action="store_true", help="apply USB gadget configuration")
    actions.add_argument("--check", action="store_true", help="inspect current configuration")
    actions.add_argument("--restore", action="store_true", help="restore the original backup")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.apply:
            apply()
        elif args.restore:
            restore()
        else:
            check()
    except (OSError, SetupError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
