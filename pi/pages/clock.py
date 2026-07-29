"""Host-authoritative clock and weather page."""

from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.pages.components import draw_header
from pi.themes import Theme


class ClockPage:
    page_id = "clock"
    revision = 0
    continuous_updates = False
    partial_update_row = 300

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        canvas.clear(theme.background)
        draw_header(
            canvas,
            "CLOCK",
            connected=context.snapshot.connected,
            theme=theme,
        )
        state = context.snapshot.state
        clock = state.clock if state else None
        weather = state.weather if state else None
        time_text = clock.time_text if clock else "--:--:--"
        date_text = clock.date_text if clock else "WAITING FOR HOST TIME"

        time_width = canvas.text_width(time_text, 6)
        canvas.draw_text(
            (canvas.width - time_width) // 2,
            78,
            time_text,
            theme.text,
            scale=6,
        )
        date_width = canvas.text_width(date_text, 2)
        canvas.draw_text(
            max(12, (canvas.width - date_width) // 2),
            142,
            date_text[:39],
            theme.text_muted,
            scale=2,
        )

        canvas.fill_rect(48, 194, canvas.width - 96, 78, theme.surface)
        canvas.stroke_rect(48, 194, canvas.width - 96, 78, theme.grid)
        if weather is None:
            temperature = "--C"
            condition = "WAITING FOR WEATHER"
        else:
            temperature = f"{weather.temperature_c:.0f}C"
            condition = weather.condition
        canvas.draw_text(68, 214, temperature, theme.accent, scale=3)
        canvas.draw_text(174, 222, condition[:38], theme.text)
        canvas.draw_text(174, 241, "HOST WEATHER SOURCE", theme.text_muted)
