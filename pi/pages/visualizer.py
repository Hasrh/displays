"""Full-screen audio visualizer page."""

from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.pages.components import draw_header
from pi.themes import Theme


class VisualizerPage:
    page_id = "visualizer"
    revision = 0
    continuous_updates = True
    partial_update_row = 82

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        canvas.clear(theme.background)
        draw_header(
            canvas,
            "VISUALIZER",
            connected=context.snapshot.connected,
            theme=theme,
        )
        media = context.snapshot.state.media if context.snapshot.state else None
        canvas.draw_text(14, 52, (media.title if media else "WAITING FOR AUDIO")[:55], theme.text)
        canvas.draw_text(
            14,
            67,
            (media.artist if media else "SYNTHETIC FFT")[:55],
            theme.text_muted,
        )
        self._bars(canvas, context.fft_bins, theme)

    @staticmethod
    def _bars(canvas: RGB565Canvas, bins: tuple[float, ...], theme: Theme) -> None:
        left = 12
        top = 88
        width = canvas.width - 24
        height = canvas.height - top - 12
        canvas.fill_rect(left, top, width, height, theme.surface)
        for fraction in (0.25, 0.5, 0.75):
            y = top + int(height * fraction)
            canvas.fill_rect(left, y, width, 1, theme.grid)

        count = 48
        gap = 2
        bar_width = max(2, (width - gap * (count + 1)) // count)
        usable_height = height - 14
        for index in range(count):
            source = int(index * len(bins) / count) if bins else 0
            level = bins[source] if source < len(bins) else 0.0
            bar_height = max(2, int(level * usable_height))
            x = left + gap + index * (bar_width + gap)
            y = top + height - 7 - bar_height
            if level > 0.86:
                color = theme.warning
            elif level > 0.62:
                color = theme.success
            else:
                color = theme.accent
            canvas.fill_rect(x, y, bar_width, bar_height, color)
