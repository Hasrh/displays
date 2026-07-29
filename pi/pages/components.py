"""Shared page chrome and formatting helpers."""

from pi.canvas import RGB565Canvas
from pi.themes import Theme


def draw_header(
    canvas: RGB565Canvas,
    title: str,
    *,
    connected: bool,
    theme: Theme,
) -> None:
    canvas.fill_rect(0, 0, canvas.width, 38, theme.surface)
    canvas.fill_rect(0, 37, canvas.width, 1, theme.grid)
    canvas.draw_text(12, 11, title, theme.text, scale=2)
    status = "ONLINE" if connected else "OFFLINE"
    status_color = theme.success if connected else theme.danger
    width = canvas.text_width(status)
    canvas.fill_rect(canvas.width - width - 24, 10, width + 12, 17, theme.surface_alt)
    canvas.draw_text(canvas.width - width - 18, 15, status, status_color)


def draw_page_indicator(
    canvas: RGB565Canvas,
    *,
    page_count: int,
    selected_index: int,
    theme: Theme,
) -> None:
    block_width = 12
    gap = 6
    total = page_count * block_width + max(0, page_count - 1) * gap
    left = (canvas.width - total) // 2
    for index in range(page_count):
        color = theme.accent if index == selected_index else theme.grid
        canvas.fill_rect(
            left + index * (block_width + gap), canvas.height - 5, block_width, 2, color
        )


def duration_text(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"{whole // 60}:{whole % 60:02d}"
