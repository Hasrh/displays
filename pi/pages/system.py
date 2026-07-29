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
        self._details(canvas, context, theme)
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
        gpus = system.gpus if system else ()
        first_gpu = gpus[0].usage_percent if len(gpus) >= 1 else None
        second_gpu = gpus[1].usage_percent if len(gpus) >= 2 else None
        if not gpus and system is not None:
            first_gpu = system.gpu_usage_percent
        values = (
            ("CPU", system.cpu_usage_percent if system else None, "%", 100.0, theme.accent),
            ("GPU1", first_gpu, "%", 100.0, theme.warning),
            ("GPU2", second_gpu, "%", 100.0, theme.danger),
            ("RAM", system.ram_usage_percent if system else None, "%", 100.0, theme.success),
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
    def _details(canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        state = context.snapshot.state
        system = state.system if state else None
        network = state.network if state else None
        gpus = system.gpus if system else ()
        for index in range(2):
            if index < len(gpus):
                gpu = gpus[index]
                usage = "--" if gpu.usage_percent is None else f"{gpu.usage_percent:.0f}%"
                detail = f"GPU{index + 1} {usage} {gpu.name}"
            else:
                detail = f"GPU{index + 1} -- NOT AVAILABLE"
            canvas.draw_text(
                12,
                135 + index * 15,
                detail[:55],
                theme.text if index == 0 else theme.text_muted,
            )
        if network is None:
            network_text = "NETWORK --"
        else:
            down = network.download_bytes_per_second / 125_000.0
            up = network.upload_bytes_per_second / 125_000.0
            network_text = f"NETWORK DOWN {down:.1f}M  UP {up:.1f}M"
        canvas.draw_text(12, 169, network_text[:55], theme.accent)

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
