"""Fixed-rate renderer and framebuffer test primitives."""

import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress
from time import monotonic

from pi.animations import PageTransition, ProgressPulse, SmoothedBins
from pi.assets import AssetCache
from pi.canvas import RGB565Canvas
from pi.display import DisplayBackend
from pi.pages import Page, RenderContext, SystemVisualizerPage
from pi.state import LatestStateStore
from pi.themes import DARK_THEME, Theme

RGB = tuple[int, int, int]
LOGGER = logging.getLogger(__name__)

TEST_COLORS: tuple[RGB, ...] = (
    (255, 255, 255),
    (255, 255, 0),
    (0, 255, 255),
    (0, 255, 0),
    (255, 0, 255),
    (255, 0, 0),
    (0, 0, 255),
    (0, 0, 0),
)


def rgb565_pixel(red: int, green: int, blue: int) -> bytes:
    """Encode an RGB888 color as little-endian RGB565."""

    if not all(0 <= component <= 255 for component in (red, green, blue)):
        raise ValueError("RGB components must be between 0 and 255")
    value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return value.to_bytes(2, byteorder="little")


def color_bars_rgb565(
    width: int,
    height: int,
    colors: Sequence[RGB] = TEST_COLORS,
) -> bytes:
    """Build a deterministic full-screen RGB565 hardware test frame."""

    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    if not colors:
        raise ValueError("at least one test color is required")

    rows = bytearray()
    for y in range(height):
        color = colors[min(y * len(colors) // height, len(colors) - 1)]
        rows.extend(rgb565_pixel(*color) * width)
    return bytes(rows)


class FixedRateRenderer:
    """Renders immutable state snapshots without waiting on network I/O."""

    def __init__(
        self,
        display: DisplayBackend,
        store: LatestStateStore,
        target_fps: int,
        *,
        page: Page | None = None,
        theme: Theme = DARK_THEME,
        assets: AssetCache | None = None,
        animations_enabled: bool = True,
    ) -> None:
        if target_fps <= 0:
            raise ValueError("target_fps must be positive")
        self.display = display
        self.store = store
        self.target_fps = target_fps
        self.page = page or SystemVisualizerPage()
        self.theme = theme
        self.assets = assets
        self.animations_enabled = animations_enabled
        self.canvas = RGB565Canvas(display.width, display.height)
        self._smoother = SmoothedBins(64)
        self._progress_pulse = ProgressPulse()
        self._page_transition = PageTransition()
        self._target_bins: tuple[float, ...] | None = None
        self._last_frame_time = monotonic()
        self.measured_fps = 0.0
        self.missed_deadlines = 0
        self.last_render_ms = 0.0
        self.last_write_ms = 0.0
        self.last_write_was_full = True
        self.last_write_performed = True
        self._has_written_frame = False
        self._last_state: object = object()
        self._last_connected: bool | None = None
        self._last_page_revision = -1
        self._last_asset_revision = -1

    def render_once(self, now: float | None = None) -> None:
        frame_time = monotonic() if now is None else now
        render_started = monotonic()
        delta = frame_time - self._last_frame_time
        self._last_frame_time = frame_time
        snapshot = self.store.snapshot()
        fft = self.store.consume_fft()
        if fft is not None:
            self._target_bins = fft.bins
        if not snapshot.connected:
            self._target_bins = None
        bins = self._smoother.update(self._target_bins, delta)
        media = snapshot.state.media if snapshot.state is not None else None
        playing = bool(media and media.is_playing)
        pulse = (
            self._progress_pulse.update(delta, active=playing) if self.animations_enabled else 1.0
        )
        page_revision = self.page.revision
        self._page_transition.observe(page_revision)
        transition = self._page_transition.update(delta) if self.animations_enabled else 1.0
        asset_revision = 0 if self.assets is None else self.assets.revision
        self.page.render(
            self.canvas,
            RenderContext(
                snapshot=snapshot,
                fft_bins=bins,
                measured_fps=self.measured_fps,
                assets=self.assets,
                progress_pulse=pulse,
                transition_progress=transition,
                now_seconds=frame_time,
            ),
            self.theme,
        )
        if self.animations_enabled and transition < 1.0:
            cover = int(self.canvas.width * (1.0 - transition))
            if cover > 0:
                self.canvas.fill_rect(0, 0, cover, self.canvas.height, self.theme.background)
        write_started = monotonic()
        full_update = (
            not self._has_written_frame
            or snapshot.state is not self._last_state
            or snapshot.connected != self._last_connected
            or page_revision != self._last_page_revision
            or asset_revision != self._last_asset_revision
            or (self.animations_enabled and self._page_transition.active)
        )
        if full_update:
            self.display.write_frame(self.canvas.frame())
        elif self.page.continuous_updates:
            self.display.write_rows(
                self.canvas.frame(),
                self.page.partial_update_row,
                self.display.height,
            )
        completed = monotonic()
        self.last_render_ms = (write_started - render_started) * 1000.0
        write_performed = full_update or self.page.continuous_updates
        self.last_write_ms = (completed - write_started) * 1000.0 if write_performed else 0.0
        self.last_write_was_full = full_update
        self.last_write_performed = write_performed
        self._has_written_frame = True
        self._last_state = snapshot.state
        self._last_connected = snapshot.connected
        self._last_page_revision = page_revision
        self._last_asset_revision = asset_revision

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        interval = 1.0 / self.target_fps
        next_frame = monotonic()
        report_started = next_frame
        report_frames = 0
        report_render_ms = 0.0
        report_write_ms = 0.0
        report_full_writes = 0
        report_writes = 0
        self.display.open()
        try:
            while not stop.is_set():
                self.render_once()
                report_frames += 1
                report_render_ms += self.last_render_ms
                report_write_ms += self.last_write_ms
                report_full_writes += int(self.last_write_was_full)
                report_writes += int(self.last_write_performed)
                now = monotonic()
                if now - report_started >= 5.0:
                    self.measured_fps = report_frames / (now - report_started)
                    LOGGER.info(
                        "Renderer fps=%.1f target=%d render_ms=%.1f write_ms=%.1f "
                        "writes=%d/%d full_writes=%d missed_deadlines=%d",
                        self.measured_fps,
                        self.target_fps,
                        report_render_ms / report_frames,
                        report_write_ms / max(1, report_writes),
                        report_writes,
                        report_frames,
                        report_full_writes,
                        self.missed_deadlines,
                    )
                    report_started = now
                    report_frames = 0
                    report_render_ms = 0.0
                    report_write_ms = 0.0
                    report_full_writes = 0
                    report_writes = 0

                next_frame += interval
                delay = next_frame - monotonic()
                if delay <= 0:
                    self.missed_deadlines += 1
                    next_frame = monotonic()
                    await asyncio.sleep(0)
                else:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=delay)
        finally:
            self.display.close()
