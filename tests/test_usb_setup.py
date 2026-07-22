"""Pure transformation tests for the Bookworm USB gadget setup."""

import pytest

from scripts.setup_usb_gadget_bookworm import (
    DEVICE_MAC,
    GADGET_OVERLAY,
    HOST_MAC,
    SetupError,
    update_cmdline_text,
    update_config_text,
)


def test_replaces_host_mode_without_touching_display_overlay() -> None:
    original = """
[all]
dtoverlay=dwc2,dr_mode=host
dtparam=spi=on
dtoverlay=tft35a:rotate=90
""".lstrip()
    updated = update_config_text(original)
    assert updated.count(GADGET_OVERLAY) == 1
    assert "dr_mode=host" not in updated
    assert "dtoverlay=tft35a:rotate=90" in updated


def test_appends_peripheral_overlay_when_missing() -> None:
    updated = update_config_text("dtparam=spi=on\n")
    assert updated.endswith(f"[all]\n{GADGET_OVERLAY}\n")


def test_cmdline_adds_modules_and_stable_macs_idempotently() -> None:
    original = "console=serial0,115200 rootwait modules-load=vc4\n"
    first = update_cmdline_text(original)
    second = update_cmdline_text(first)
    assert first == second
    assert "modules-load=vc4,dwc2,g_ether" in first
    assert f"g_ether.host_addr={HOST_MAC}" in first
    assert f"g_ether.dev_addr={DEVICE_MAC}" in first
    assert first.count("modules-load=") == 1


def test_rejects_multiline_cmdline() -> None:
    with pytest.raises(SetupError, match="exactly one"):
        update_cmdline_text("rootwait\nquiet\n")
