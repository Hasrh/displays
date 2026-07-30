"""Host-authoritative PC status dashboard."""

from __future__ import annotations

from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.themes import RGB, Theme

CPU_COLOR: RGB = (255, 112, 128)
MEMORY_COLOR: RGB = (64, 220, 96)
GPU_COLOR: RGB = (255, 200, 48)
CASE_COLOR: RGB = (64, 220, 255)
HEADER_COLOR: RGB = (236, 240, 244)


class SystemVisualizerPage:
    """2x2 PC status page matching the companion-display dashboard layout."""

    page_id = "system"
    revision = 0
    continuous_updates = False
    partial_update_row = 300

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        del theme
        canvas.clear((0, 0, 0))
        self._status_bar(canvas, context)
        self._panels(canvas, context)

    @staticmethod
    def _status_bar(canvas: RGB565Canvas, context: RenderContext) -> None:
        state = context.snapshot.state
        weather = state.weather if state else None
        clock = state.clock if state else None
        system = state.system if state else None

        left = "--C" if weather is None else f"{weather.temperature_c:.0f}C"
        center = "--:--"
        if clock is not None and clock.time_text:
            parts = clock.time_text.split(":")
            center = ":".join(parts[:2]) if len(parts) >= 2 else clock.time_text[:5]
        right = (
            "--%"
            if system is None or system.cpu_usage_percent is None
            else (f"{system.cpu_usage_percent:.0f}%")
        )

        canvas.draw_text(10, 8, left, HEADER_COLOR, scale=2)
        center_width = canvas.text_width(center, 2)
        canvas.draw_text((canvas.width - center_width) // 2, 8, center, HEADER_COLOR, scale=2)
        right_width = canvas.text_width(right, 2)
        canvas.draw_text(canvas.width - right_width - 10, 8, right, HEADER_COLOR, scale=2)

    def _panels(self, canvas: RGB565Canvas, context: RenderContext) -> None:
        state = context.snapshot.state
        system = state.system if state else None
        gpus = system.gpus if system else ()
        primary_gpu = gpus[0] if gpus else None
        gpu_temp = None
        gpu_fan = None
        if primary_gpu is not None:
            gpu_temp = primary_gpu.temperature_c
            gpu_fan = primary_gpu.fan_percent
        elif system is not None:
            gpu_temp = system.gpu_temperature_c

        margin = 8
        top = 34
        gap = 8
        width = (canvas.width - margin * 2 - gap) // 2
        height = (canvas.height - top - margin - gap - 6) // 2
        panels = (
            (
                margin,
                top,
                "CPU",
                CPU_COLOR,
                (
                    ("Usage", self._percent(None if system is None else system.cpu_usage_percent)),
                    ("Temp", self._temp(None if system is None else system.cpu_temperature_c)),
                    ("Fan", self._rpm(None if system is None else system.cpu_fan_rpm)),
                ),
            ),
            (
                margin + width + gap,
                top,
                "MEMORY",
                MEMORY_COLOR,
                (
                    ("Ram", self._mb(None if system is None else system.ram_used_mb)),
                    ("Hdd", self._mb(None if system is None else system.disk_used_mb)),
                ),
            ),
            (
                margin,
                top + height + gap,
                "GPU",
                GPU_COLOR,
                (
                    ("Temp", self._temp(gpu_temp)),
                    ("Fan", self._percent(gpu_fan)),
                ),
            ),
            (
                margin + width + gap,
                top + height + gap,
                "CASE",
                CASE_COLOR,
                (
                    ("Fan", self._rpm(None if system is None else system.case_fan_rpm)),
                    ("Temp", self._temp(None if system is None else system.case_temperature_c)),
                ),
            ),
        )
        for x, y, title, color, rows in panels:
            self._panel(canvas, x, y, width, height, title, color, rows)

    @staticmethod
    def _panel(
        canvas: RGB565Canvas,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str,
        color: RGB,
        rows: tuple[tuple[str, str], ...],
    ) -> None:
        canvas.stroke_round_rect(x, y, width, height, color, radius=10, thickness=2)
        title_width = canvas.text_width(title, 2)
        canvas.draw_text(x + (width - title_width) // 2, y + 10, title, color, scale=2)
        divider_y = y + 32
        canvas.fill_rect(x + 12, divider_y, width - 24, 1, color)

        row_top = divider_y + 14
        row_gap = 22 if len(rows) <= 2 else 18
        for index, (label, value) in enumerate(rows):
            row_y = row_top + index * row_gap
            canvas.draw_text(x + 14, row_y, f"{label}:", color, scale=2)
            value_width = canvas.text_width(value, 2)
            canvas.draw_text(x + width - 14 - value_width, row_y, value, color, scale=2)

    @staticmethod
    def _percent(value: float | None) -> str:
        return "-- %" if value is None else f"{value:.0f} %"

    @staticmethod
    def _temp(value: float | None) -> str:
        return "-- C" if value is None else f"{value:.0f} C"

    @staticmethod
    def _rpm(value: float | None) -> str:
        return "-- R" if value is None else f"{value:.0f} R"

    @staticmethod
    def _mb(value: float | None) -> str:
        if value is None:
            return "-- MB"
        if value >= 10240:
            return f"{value / 1024.0:.0f} GB"
        return f"{value:.0f} MB"
