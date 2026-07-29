"""Retro monochrome media visualizer inspired by compact hardware players."""

from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.pages.components import duration_text
from pi.themes import Theme

BLACK = (0, 0, 0)
WHITE = (238, 242, 235)
DIM = (142, 150, 142)


class VisualizerPage:
    page_id = "visualizer"
    revision = 0
    continuous_updates = True
    partial_update_row = 82

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        del theme
        canvas.clear(BLACK)
        state = context.snapshot.state
        media = state.media if state else None
        clock = state.clock if state else None
        self._status_row(
            canvas,
            time_text=clock.time_text[:5] if clock else "--:--",
            volume_percent=media.volume_percent if media else None,
            connected=context.snapshot.connected,
        )
        canvas.fill_rect(28, 52, canvas.width - 56, 2, WHITE)
        canvas.draw_text(31, 68, "FFT  A-B", WHITE, scale=2)
        link = "ONLINE" if context.snapshot.connected else "OFFLINE"
        canvas.draw_text(
            canvas.width - 31 - canvas.text_width(link, 2),
            68,
            link,
            WHITE,
            scale=2,
        )
        self._bars(canvas, context.fft_bins)
        self._track_row(canvas, media)
        self._controls(canvas)

    @staticmethod
    def _status_row(
        canvas: RGB565Canvas,
        *,
        time_text: str,
        volume_percent: float | None,
        connected: bool,
    ) -> None:
        VisualizerPage._speaker(canvas, 30, 20)
        level = 0.0 if volume_percent is None else volume_percent / 100.0
        for index in range(4):
            height = 5 + index * 4
            color = WHITE if level >= (index + 1) / 4 else DIM
            canvas.fill_rect(54 + index * 7, 35 - height, 4, height, color)
        time_width = canvas.text_width(time_text, 3)
        canvas.draw_text((canvas.width - time_width) // 2, 15, time_text, WHITE, scale=3)
        VisualizerPage._link_indicator(canvas, canvas.width - 74, 18, connected)

    @staticmethod
    def _speaker(canvas: RGB565Canvas, x: int, y: int) -> None:
        canvas.fill_rect(x, y + 7, 6, 10, WHITE)
        for column in range(8):
            half_height = 2 + column // 2
            canvas.fill_rect(x + 6 + column, y + 12 - half_height, 1, half_height * 2, WHITE)

    @staticmethod
    def _link_indicator(canvas: RGB565Canvas, x: int, y: int, connected: bool) -> None:
        canvas.stroke_rect(x, y, 46, 20, WHITE, thickness=2)
        canvas.fill_rect(x + 46, y + 6, 4, 8, WHITE)
        fill_width = 36 if connected else 8
        canvas.fill_rect(x + 5, y + 5, fill_width, 10, WHITE if connected else DIM)

    @staticmethod
    def _bars(canvas: RGB565Canvas, bins: tuple[float, ...]) -> None:
        left = 42
        top = 103
        width = canvas.width - 84
        height = 82
        count = 32
        gap = 4
        bar_width = max(3, (width - gap * (count - 1)) // count)
        used_width = count * bar_width + (count - 1) * gap
        left += (width - used_width) // 2
        for index in range(count):
            first = bins[index * 2] if index * 2 < len(bins) else 0.0
            second = bins[index * 2 + 1] if index * 2 + 1 < len(bins) else first
            bar_height = max(3, int(max(first, second) * height))
            x = left + index * (bar_width + gap)
            canvas.fill_rect(x, top + height - bar_height, bar_width, bar_height, WHITE)

    @staticmethod
    def _track_row(canvas: RGB565Canvas, media: object) -> None:
        position = getattr(media, "position_seconds", 0.0)
        duration = getattr(media, "duration_seconds", 0.0)
        title = getattr(media, "title", "WAITING FOR MEDIA") or "UNTITLED"
        elapsed_text = duration_text(position)
        duration_label = duration_text(duration)
        canvas.draw_text(28, 202, elapsed_text, WHITE, scale=2)
        canvas.draw_text(
            canvas.width - 28 - canvas.text_width(duration_label, 2),
            202,
            duration_label,
            WHITE,
            scale=2,
        )
        available_width = canvas.width - 216
        maximum_characters = max(1, (available_width + 2) // 12)
        title = str(title)[:maximum_characters]
        canvas.draw_text(
            (canvas.width - canvas.text_width(title, 2)) // 2,
            202,
            title,
            WHITE,
            scale=2,
        )
        progress = position / duration if duration > 0 else 0.0
        progress = max(0.0, min(1.0, progress))
        canvas.fill_rect(28, 235, canvas.width - 56, 3, DIM)
        canvas.fill_rect(28, 235, int((canvas.width - 56) * progress), 3, WHITE)
        marker_x = 28 + int((canvas.width - 56) * progress)
        canvas.fill_rect(marker_x - 2, 231, 4, 11, WHITE)

    @staticmethod
    def _controls(canvas: RGB565Canvas) -> None:
        center_y = 275
        VisualizerPage._transport_icon(canvas, 68, center_y, "previous")
        VisualizerPage._transport_icon(canvas, 154, center_y, "rewind")
        VisualizerPage._transport_icon(canvas, 240, center_y, "play")
        VisualizerPage._transport_icon(canvas, 326, center_y, "forward")
        VisualizerPage._transport_icon(canvas, 412, center_y, "next")

    @staticmethod
    def _transport_icon(canvas: RGB565Canvas, center_x: int, center_y: int, action: str) -> None:
        if action in {"previous", "rewind"}:
            if action == "previous":
                canvas.fill_rect(center_x - 16, center_y - 10, 3, 20, WHITE)
            VisualizerPage._triangle(canvas, center_x - 11, center_y, left=True)
            VisualizerPage._triangle(canvas, center_x + 1, center_y, left=True)
        elif action == "play":
            VisualizerPage._triangle(canvas, center_x - 7, center_y, left=False, size=15)
        else:
            VisualizerPage._triangle(canvas, center_x - 12, center_y, left=False)
            VisualizerPage._triangle(canvas, center_x, center_y, left=False)
            if action == "next":
                canvas.fill_rect(center_x + 13, center_y - 10, 3, 20, WHITE)

    @staticmethod
    def _triangle(
        canvas: RGB565Canvas,
        x: int,
        center_y: int,
        *,
        left: bool,
        size: int = 11,
    ) -> None:
        for column in range(size):
            distance = column if left else size - column - 1
            half_height = max(1, int((distance + 1) * size / (size * 2)))
            canvas.fill_rect(x + column, center_y - half_height, 1, half_height * 2 + 1, WHITE)
