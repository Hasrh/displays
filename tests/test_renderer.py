"""RGB565 canvas, page, animation, and fixed-rate renderer tests."""

from pi.animations import SmoothedBins
from pi.canvas import RGB565Canvas, pack_rgb565
from pi.display import HeadlessBackend
from pi.renderer import FixedRateRenderer
from pi.state import LatestStateStore
from shared.constants import MessageType
from shared.models import DisplayState, FFTFrame, MediaState, SystemMetrics
from shared.protocol import StateSnapshotPayload, new_envelope

NOW = "2026-07-29T09:45:00Z"


def test_canvas_clips_rectangles_and_encodes_rgb565() -> None:
    canvas = RGB565Canvas(4, 3)
    canvas.clear((0, 0, 0))
    canvas.fill_rect(-1, 1, 3, 3, (255, 0, 0))
    assert len(canvas.frame()) == 24
    red = pack_rgb565((255, 0, 0))
    assert bytes(canvas.frame()[8:12]) == red * 2
    assert bytes(canvas.frame()[16:20]) == red * 2


def test_smoothing_uses_faster_attack_than_release() -> None:
    smoother = SmoothedBins(1, attack_rate=20.0, release_rate=2.0)
    attacked = smoother.update((1.0,), 0.05)[0]
    released = smoother.update((0.0,), 0.05)[0]
    assert attacked > 0.5
    assert released > 0.5


def test_renderer_writes_live_dashboard_to_headless_backend() -> None:
    store = LatestStateStore()
    store.set_connected(True)
    state = DisplayState(
        media=MediaState(
            title="Network Test",
            artist="Synthetic",
            album=None,
            is_playing=True,
            position_seconds=30.0,
            duration_seconds=120.0,
        ),
        system=SystemMetrics(
            cpu_usage_percent=42.0,
            gpu_usage_percent=55.0,
            ram_usage_percent=63.0,
        ),
    )
    store.apply(
        new_envelope(
            MessageType.STATE_SNAPSHOT,
            StateSnapshotPayload(generated_at=NOW, state=state),
            sequence=1,
            sent_at=NOW,
        )
    )
    store.apply(
        new_envelope(
            MessageType.FFT_FRAME,
            FFTFrame(captured_at=NOW, bins=(0.75,) * 64),
            sequence=2,
            sent_at=NOW,
        )
    )
    display = HeadlessBackend(480, 320)
    display.open()
    renderer = FixedRateRenderer(display, store, 10)
    renderer.render_once()
    display.close()
    assert display.last_frame is not None
    assert len(display.last_frame) == 480 * 320 * 2
    assert any(display.last_frame)
