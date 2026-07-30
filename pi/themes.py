"""Semantic color tokens for renderer pages."""

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
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
    name="dark",
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

CYBERPUNK_THEME = Theme(
    name="cyberpunk",
    background=(8, 4, 18),
    surface=(24, 10, 36),
    surface_alt=(40, 16, 56),
    text=(236, 244, 255),
    text_muted=(140, 120, 168),
    accent=(0, 229, 255),
    success=(57, 255, 160),
    warning=(255, 214, 64),
    danger=(255, 64, 129),
    grid=(78, 36, 110),
)

MINIMAL_THEME = Theme(
    name="minimal",
    background=(18, 18, 18),
    surface=(28, 28, 28),
    surface_alt=(40, 40, 40),
    text=(238, 238, 238),
    text_muted=(140, 140, 140),
    accent=(210, 210, 210),
    success=(170, 210, 170),
    warning=(210, 190, 140),
    danger=(210, 140, 140),
    grid=(64, 64, 64),
)

RETRO_THEME = Theme(
    name="retro",
    background=(12, 18, 12),
    surface=(20, 32, 20),
    surface_alt=(30, 46, 30),
    text=(198, 236, 170),
    text_muted=(110, 150, 110),
    accent=(120, 220, 90),
    success=(90, 200, 90),
    warning=(210, 200, 70),
    danger=(200, 90, 70),
    grid=(48, 78, 48),
)

THEMES: dict[str, Theme] = {
    DARK_THEME.name: DARK_THEME,
    CYBERPUNK_THEME.name: CYBERPUNK_THEME,
    MINIMAL_THEME.name: MINIMAL_THEME,
    RETRO_THEME.name: RETRO_THEME,
}


def get_theme(name: str) -> Theme:
    try:
        return THEMES[name]
    except KeyError as exc:
        supported = ", ".join(sorted(THEMES))
        raise ValueError(f"unknown theme {name!r}; expected one of {supported}") from exc
