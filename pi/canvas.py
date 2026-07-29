"""Allocation-conscious RGB565 drawing surface for the Pi Zero."""

from __future__ import annotations

from pi.fonts import GLYPHS
from pi.themes import RGB


def pack_rgb565(color: RGB) -> bytes:
    red, green, blue = color
    if not all(0 <= component <= 255 for component in color):
        raise ValueError("RGB components must be between 0 and 255")
    value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return value.to_bytes(2, "little")


class RGB565Canvas:
    """Mutable full-frame canvas matching the verified framebuffer format."""

    bytes_per_pixel = 2

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
        self.width = width
        self.height = height
        self.buffer = bytearray(width * height * self.bytes_per_pixel)

    def clear(self, color: RGB) -> None:
        self.buffer[:] = pack_rgb565(color) * (self.width * self.height)

    def fill_rect(self, x: int, y: int, width: int, height: int, color: RGB) -> None:
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if right <= left or bottom <= top:
            return
        row = pack_rgb565(color) * (right - left)
        stride = self.width * self.bytes_per_pixel
        start_x = left * self.bytes_per_pixel
        for row_index in range(top, bottom):
            start = row_index * stride + start_x
            self.buffer[start : start + len(row)] = row

    def stroke_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: RGB,
        *,
        thickness: int = 1,
    ) -> None:
        if thickness <= 0:
            return
        self.fill_rect(x, y, width, thickness, color)
        self.fill_rect(x, y + height - thickness, width, thickness, color)
        self.fill_rect(x, y, thickness, height, color)
        self.fill_rect(x + width - thickness, y, thickness, height, color)

    @staticmethod
    def text_width(text: str, scale: int = 1) -> int:
        if scale <= 0:
            raise ValueError("text scale must be positive")
        return max(0, len(text) * 6 * scale - scale)

    def draw_text(
        self,
        x: int,
        y: int,
        text: str,
        color: RGB,
        *,
        scale: int = 1,
    ) -> None:
        if scale <= 0:
            raise ValueError("text scale must be positive")
        cursor = x
        for character in text.upper():
            glyph = GLYPHS.get(character, GLYPHS["?"])
            for row_index, bits in enumerate(glyph):
                for column in range(5):
                    if bits & (1 << (4 - column)):
                        self.fill_rect(
                            cursor + column * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor += 6 * scale

    def frame(self) -> memoryview:
        return memoryview(self.buffer)
