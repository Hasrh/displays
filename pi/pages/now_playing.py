"""Now Playing page."""

from pi.animations import scale_rgb
from pi.canvas import RGB565Canvas
from pi.pages.base import RenderContext
from pi.pages.components import draw_header, duration_text
from pi.themes import Theme


class NowPlayingPage:
    page_id = "now_playing"
    revision = 0
    continuous_updates = True
    partial_update_row = 230

    def render(self, canvas: RGB565Canvas, context: RenderContext, theme: Theme) -> None:
        canvas.clear(theme.background)
        draw_header(
            canvas,
            "NOW PLAYING",
            connected=context.snapshot.connected,
            theme=theme,
        )
        media = context.snapshot.state.media if context.snapshot.state else None
        art_id = media.album_art_id if media else None
        self._album_art(canvas, context, theme, art_id)

        title = media.title if media else "WAITING FOR MEDIA"
        artist = media.artist if media else "NO HOST STATE"
        album = media.album if media and media.album else "UNKNOWN ALBUM"
        canvas.draw_text(194, 67, title[:22], theme.text, scale=2)
        canvas.draw_text(194, 105, artist[:38], theme.accent)
        canvas.draw_text(194, 124, album[:38], theme.text_muted)

        playing = bool(media and media.is_playing)
        canvas.fill_rect(194, 153, 74, 22, theme.surface_alt)
        canvas.draw_text(
            204,
            161,
            "PLAYING" if playing else "PAUSED",
            theme.success if playing else theme.warning,
        )

        position = media.position_seconds if media else 0.0
        duration = media.duration_seconds if media else 0.0
        progress = position / duration if duration > 0 else 0.0
        bar_width = canvas.width - 36
        filled = int(bar_width * progress)
        canvas.fill_rect(18, 238, bar_width, 8, theme.surface_alt)
        if filled > 0:
            accent = scale_rgb(theme.accent, context.progress_pulse if playing else 1.0)
            canvas.fill_rect(18, 238, filled, 8, accent)
        canvas.draw_text(18, 258, duration_text(position), theme.text_muted)
        remaining = duration_text(duration)
        canvas.draw_text(
            canvas.width - 18 - canvas.text_width(remaining),
            258,
            remaining,
            theme.text_muted,
        )
        canvas.draw_text(18, 288, "HOST AUTHORITATIVE MEDIA", theme.text_muted)

    @staticmethod
    def _album_art(
        canvas: RGB565Canvas,
        context: RenderContext,
        theme: Theme,
        art_id: str | None,
    ) -> None:
        x, y, size = 18, 58, 152
        pixels = context.album_art(art_id)
        if pixels is not None:
            canvas.blit_rgb565(x, y, pixels)
            canvas.stroke_rect(x, y, size, size, theme.grid, thickness=2)
            return
        canvas.fill_rect(x, y, size, size, theme.surface)
        canvas.stroke_rect(x, y, size, size, theme.grid, thickness=2)
        for inset, color in (
            (18, theme.surface_alt),
            (36, theme.grid),
            (54, theme.surface_alt),
        ):
            canvas.stroke_rect(
                x + inset,
                y + inset,
                size - inset * 2,
                size - inset * 2,
                color,
                thickness=4,
            )
        label = "ART"
        canvas.draw_text(
            x + (size - canvas.text_width(label, 2)) // 2,
            y + 66,
            label,
            theme.text_muted,
            scale=2,
        )
