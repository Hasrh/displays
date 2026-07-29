"""Latest-value Pi state-store tests."""

from pi.state import LatestStateStore
from shared.constants import MessageType
from shared.models import DisplayState, FFTFrame, SystemMetrics
from shared.protocol import StatePatchPayload, StateSnapshotPayload, new_envelope

NOW = "2026-07-29T08:45:00Z"


def test_store_merges_patch_and_drops_stale_messages() -> None:
    store = LatestStateStore()
    snapshot = new_envelope(
        MessageType.STATE_SNAPSHOT,
        StateSnapshotPayload(
            generated_at=NOW,
            state=DisplayState(system=SystemMetrics(cpu_usage_percent=20.0)),
        ),
        sequence=1,
        sent_at=NOW,
    )
    patch = new_envelope(
        MessageType.STATE_PATCH,
        StatePatchPayload(
            base_sequence=1,
            changes={"system": {"gpu_usage_percent": 55.0}},
        ),
        sequence=2,
        sent_at=NOW,
    )
    assert store.apply(snapshot)
    assert store.apply(patch)
    assert not store.apply(snapshot)
    state = store.snapshot().state
    assert state is not None
    assert state.system is not None
    assert state.system.cpu_usage_percent == 20.0
    assert state.system.gpu_usage_percent == 55.0


def test_store_keeps_only_latest_fft_frame() -> None:
    store = LatestStateStore()
    first = new_envelope(
        MessageType.FFT_FRAME,
        FFTFrame(captured_at=NOW, bins=(0.1,) * 64),
        sequence=1,
        sent_at=NOW,
    )
    second = new_envelope(
        MessageType.FFT_FRAME,
        FFTFrame(captured_at=NOW, bins=(0.9,) * 64),
        sequence=2,
        sent_at=NOW,
    )
    assert store.apply(first)
    assert store.apply(second)
    assert store.snapshot().dropped_fft_frames == 1
    latest = store.consume_fft()
    assert latest is not None
    assert latest.bins[0] == 0.9
    assert store.consume_fft() is None
