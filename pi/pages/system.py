"""Combined system dashboard and FFT transport-validation page."""

from __future__ import annotations

from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.pages.components import draw_header
from pi.themes import RGB, Theme


class SystemVisualizerPage:
    """First production page, driven entirely by host-authoritative state."""

    page_id = "system"
    revision = 0
    continuous_updates = True
    partial_update_row = 190

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        canvas.clear(theme.background)
        self._header(canvas, context, theme)
        self._metrics(canvas, context, theme)
        self._playback(canvas, context, theme)
        self._visualizer(canvas, context.fft_bins, theme)

    @staticmethod
    def _header(canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        draw_header(
            canvas,
            "SYSTEM",
            connected=context.snapshot.connected,
            theme=theme,
        )

    def _metrics(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        state = context.snapshot.state
        system = state.system if state is not None else None
        network = state.network if state is not None else None
        values = (
            ("CPU", system.cpu_usage_percent if system else None, "%", 100.0, theme.accent),
            ("GPU", system.gpu_usage_percent if system else None, "%", 100.0, theme.warning),
            ("RAM", system.ram_usage_percent if system else None, "%", 100.0, theme.success),
            (
                "DOWN",
                network.download_bytes_per_second / 125_000.0 if network else None,
                "M",
                10.0,
                theme.accent,
            ),
        )
        gap = 8
        margin = 12
        card_width = (canvas.width - margin * 2 - gap * 3) // 4
        for index, (label, value, suffix, maximum, color) in enumerate(values):
            self._metric_card(
                canvas,
                margin + index * (card_width + gap),
                50,
                card_width,
                label,
                value,
                suffix,
                maximum,
                color,
                theme,
            )

    @staticmethod
    def _metric_card(
        canvas: RGB565Canvas,
        x: int,
        y: int,
        width: int,
        label: str,
        value: float | None,
        suffix: str,
        maximum: float,
        color: RGB,
        theme: Theme,
    ) -> None:
        height = 72
        canvas.fill_rect(x, y, width, height, theme.surface)
        canvas.stroke_rect(x, y, width, height, theme.grid)
        canvas.draw_text(x + 8, y + 8, label, theme.text_muted)
        rendered = "--" if value is None else f"{value:.0f}{suffix}"
        canvas.draw_text(x + 8, y + 27, rendered, theme.text, scale=2)
        normalized = 0.0 if value is None else max(0.0, min(1.0, value / maximum))
        canvas.fill_rect(x + 8, y + 60, width - 16, 4, theme.surface_alt)
        canvas.fill_rect(x + 8, y + 60, int((width - 16) * normalized), 4, color)

    @staticmethod
    def _playback(canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        media = context.snapshot.state.media if context.snapshot.state else None
        title = media.title if media else "WAITING FOR HOST STATE"
        artist = media.artist if media else "SYNTHETIC TRANSPORT"
        canvas.draw_text(12, 137, title[:50], theme.text)
        canvas.draw_text(12, 151, artist[:50], theme.text_muted)
        progress = (
            media.position_seconds / media.duration_seconds
            if media is not None and media.duration_seconds > 0
            else 0.0
        )
        canvas.fill_rect(12, 169, canvas.width - 24, 4, theme.surface_alt)
        canvas.fill_rect(12, 169, int((canvas.width - 24) * progress), 4, theme.accent)

    @staticmethod
    def _visualizer(canvas: RGB565Canvas, bins: tuple[float, ...], theme: Theme) -> None:
        left = 12
        top = 190
        width = canvas.width - 24
        height = canvas.height - top - 12
        canvas.fill_rect(left, top, width, height, theme.surface)
        for fraction in (0.25, 0.5, 0.75):
            y = top + int(height * fraction)
            canvas.fill_rect(left, y, width, 1, theme.grid)

        bar_count = 32
        gap = 3
        bar_width = max(2, (width - gap * (bar_count + 1)) // bar_count)
        usable_height = height - 12
        for index in range(bar_count):
            first = bins[index * 2] if index * 2 < len(bins) else 0.0
            second = bins[index * 2 + 1] if index * 2 + 1 < len(bins) else first
            level = max(first, second)
            bar_height = max(2, int(level * usable_height))
            x = left + gap + index * (bar_width + gap)
            y = top + height - 6 - bar_height
            color = theme.warning if level > 0.82 else theme.accent
            canvas.fill_rect(x, y, bar_width, bar_height, color)
