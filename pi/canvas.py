"""Allocation-conscious RGB565 drawing surface for the Pi Zero."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from pi.fonts import GLYPHS
from pi.themes import RGB


def pack_rgb565_value(color: RGB) -> int:
    red, green, blue = color
    if not all(0 <= component <= 255 for component in color):
        raise ValueError("RGB components must be between 0 and 255")
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def pack_rgb565(color: RGB) -> bytes:
    return pack_rgb565_value(color).to_bytes(2, "little")


@lru_cache(maxsize=512)
def _text_mask(text: str, scale: int) -> NDArray[np.bool_]:
    width = RGB565Canvas.text_width(text, scale)
    base = np.zeros((7, max(0, width // scale)), dtype=np.bool_)
    cursor = 0
    for character in text:
        glyph = GLYPHS.get(character, GLYPHS["?"])
        for row_index, bits in enumerate(glyph):
            for column in range(5):
                if bits & (1 << (4 - column)):
                    base[row_index, cursor + column] = True
        cursor += 6
    if scale == 1:
        return base
    return np.repeat(np.repeat(base, scale, axis=0), scale, axis=1)


class RGB565Canvas:
    """Mutable full-frame canvas matching the verified framebuffer format."""

    bytes_per_pixel = 2

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
        self.width = width
        self.height = height
        self._pixels: NDArray[np.uint16] = np.zeros((height, width), dtype="<u2")

    def clear(self, color: RGB) -> None:
        self._pixels.fill(pack_rgb565_value(color))

    def fill_rect(self, x: int, y: int, width: int, height: int, color: RGB) -> None:
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if right <= left or bottom <= top:
            return
        self._pixels[top:bottom, left:right] = pack_rgb565_value(color)

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

    def stroke_round_rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: RGB,
        *,
        radius: int = 8,
        thickness: int = 1,
    ) -> None:
        """Approximate a rounded rectangle with clipped corner strokes."""

        if thickness <= 0 or width <= 0 or height <= 0:
            return
        corner = max(0, min(radius, width // 2, height // 2))
        if corner == 0:
            self.stroke_rect(x, y, width, height, color, thickness=thickness)
            return
        self.fill_rect(x + corner, y, width - corner * 2, thickness, color)
        self.fill_rect(x + corner, y + height - thickness, width - corner * 2, thickness, color)
        self.fill_rect(x, y + corner, thickness, height - corner * 2, color)
        self.fill_rect(x + width - thickness, y + corner, thickness, height - corner * 2, color)
        centers = (
            (x + corner, y + corner, -1, -1),
            (x + width - corner - 1, y + corner, 1, -1),
            (x + corner, y + height - corner - 1, -1, 1),
            (x + width - corner - 1, y + height - corner - 1, 1, 1),
        )
        outer = corner * corner
        inner = max(0, corner - thickness) ** 2
        packed = pack_rgb565_value(color)
        for center_x, center_y, sign_x, sign_y in centers:
            for row in range(corner):
                for column in range(corner):
                    distance = row * row + column * column
                    if not inner < distance <= outer:
                        continue
                    px = center_x + sign_x * column
                    py = center_y + sign_y * row
                    if 0 <= px < self.width and 0 <= py < self.height:
                        self._pixels[py, px] = packed

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
        mask = _text_mask(text.upper(), scale)
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + mask.shape[1])
        bottom = min(self.height, y + mask.shape[0])
        if right <= left or bottom <= top:
            return
        mask_left = left - x
        mask_top = top - y
        clipped_mask = mask[
            mask_top : mask_top + (bottom - top),
            mask_left : mask_left + (right - left),
        ]
        region = self._pixels[top:bottom, left:right]
        region[clipped_mask] = pack_rgb565_value(color)

    def blit_rgb565(
        self,
        x: int,
        y: int,
        pixels: NDArray[np.uint16],
    ) -> None:
        """Copy a little-endian RGB565 image into the canvas with clipping."""

        if pixels.ndim != 2:
            raise ValueError("RGB565 blit source must be a 2D array")
        height, width = pixels.shape
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if right <= left or bottom <= top:
            return
        source_left = left - x
        source_top = top - y
        self._pixels[top:bottom, left:right] = pixels[
            source_top : source_top + (bottom - top),
            source_left : source_left + (right - left),
        ]

    def frame(self) -> memoryview:
        return self._pixels.data.cast("B")
