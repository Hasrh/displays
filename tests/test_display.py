"""Display backend and RGB565 renderer tests."""

import pytest

from pi.display import DisplayError, HeadlessBackend
from pi.renderer import color_bars_rgb565, rgb565_pixel


def test_rgb565_primary_colors() -> None:
    assert rgb565_pixel(255, 0, 0) == b"\x00\xf8"
    assert rgb565_pixel(0, 255, 0) == b"\xe0\x07"
    assert rgb565_pixel(0, 0, 255) == b"\x1f\x00"


def test_color_bars_have_exact_frame_size() -> None:
    frame = color_bars_rgb565(480, 320)
    assert len(frame) == 480 * 320 * 2


def test_headless_backend_captures_frame() -> None:
    display = HeadlessBackend(4, 2)
    frame = color_bars_rgb565(4, 2)
    display.open()
    display.write_frame(frame)
    display.close()
    assert display.last_frame == frame


def test_headless_backend_rejects_wrong_frame_size() -> None:
    display = HeadlessBackend(4, 2)
    display.open()
    with pytest.raises(DisplayError, match="expected 16"):
        display.write_frame(b"\x00\x00")


def test_headless_backend_updates_selected_rows() -> None:
    display = HeadlessBackend(2, 3)
    display.open()
    display.write_frame(b"\x00\x00" * 6)
    changed = b"\xff\xff" * 6
    display.write_rows(changed, 1, 2)
    assert display.last_frame == b"\x00\x00" * 2 + b"\xff\xff" * 2 + b"\x00\x00" * 2
