"""Semantic color tokens for renderer pages."""

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Theme:
    background: RGB
    surface: RGB
    surface_alt: RGB
    text: RGB
    text_muted: RGB
    accent: RGB
    success: RGB
    warning: RGB
    danger: RGB
    grid: RGB


DARK_THEME = Theme(
    background=(7, 10, 16),
    surface=(15, 21, 31),
    surface_alt=(22, 31, 45),
    text=(232, 239, 247),
    text_muted=(125, 142, 160),
    accent=(42, 196, 214),
    success=(71, 201, 126),
    warning=(241, 180, 55),
    danger=(235, 91, 91),
    grid=(39, 52, 68),
)
