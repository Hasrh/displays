"""Small rendering primitives shared by display backends."""

from collections.abc import Sequence

RGB = tuple[int, int, int]

TEST_COLORS: tuple[RGB, ...] = (
    (255, 255, 255),
    (255, 255, 0),
    (0, 255, 255),
    (0, 255, 0),
    (255, 0, 255),
    (255, 0, 0),
    (0, 0, 255),
    (0, 0, 0),
)


def rgb565_pixel(red: int, green: int, blue: int) -> bytes:
    """Encode an RGB888 color as little-endian RGB565."""

    if not all(0 <= component <= 255 for component in (red, green, blue)):
        raise ValueError("RGB components must be between 0 and 255")
    value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return value.to_bytes(2, byteorder="little")


def color_bars_rgb565(
    width: int,
    height: int,
    colors: Sequence[RGB] = TEST_COLORS,
) -> bytes:
    """Build a deterministic full-screen RGB565 hardware test frame."""

    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    if not colors:
        raise ValueError("at least one test color is required")

    rows = bytearray()
    for y in range(height):
        color = colors[min(y * len(colors) // height, len(colors) - 1)]
        rows.extend(rgb565_pixel(*color) * width)
    return bytes(rows)
