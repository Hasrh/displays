"""Latest-value state store for the Raspberry Pi renderer."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from shared.constants import MessageType
from shared.models import DisplayState, FFTFrame
from shared.protocol import Envelope, StatePatchPayload, StateSnapshotPayload


@dataclass(frozen=True, slots=True)
class StoreSnapshot:
    connected: bool
    state: DisplayState | None
    latest_fft: FFTFrame | None
    last_sequence: int
    dropped_fft_frames: int
    updated_monotonic: float


class LatestStateStore:
    """Keeps only render-relevant current values; it never queues FFT history."""

    def __init__(self) -> None:
        self._connected = False
        self._state: DisplayState | None = None
        self._latest_fft: FFTFrame | None = None
        self._last_sequence = -1
        self._state_base_sequence = -1
        self._dropped_fft_frames = 0
        self._updated_monotonic = monotonic()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._updated_monotonic = monotonic()

    def reset_session(self) -> None:
        self._last_sequence = -1
        self._state_base_sequence = -1
        self._latest_fft = None

    def apply(self, envelope: Envelope) -> bool:
        """Apply a state-bearing envelope, returning false when it is stale."""

        if envelope.sequence <= self._last_sequence:
            return False
        payload = envelope.payload
        if envelope.type is MessageType.STATE_SNAPSHOT:
            if not isinstance(payload, StateSnapshotPayload):
                return False
            self._state = payload.state
            self._state_base_sequence = envelope.sequence
        elif envelope.type is MessageType.STATE_PATCH:
            if not isinstance(payload, StatePatchPayload):
                return False
            if self._state is None or payload.base_sequence != self._state_base_sequence:
                return False
            self._state = self._apply_patch(self._state, payload)
        elif envelope.type is MessageType.FFT_FRAME:
            if not isinstance(payload, FFTFrame):
                return False
            if self._latest_fft is not None:
                self._dropped_fft_frames += 1
            self._latest_fft = payload
        else:
            return False

        self._last_sequence = envelope.sequence
        self._updated_monotonic = monotonic()
        return True

    @staticmethod
    def _apply_patch(current: DisplayState, patch: StatePatchPayload) -> DisplayState:
        document = current.to_dict()
        for section, change in patch.changes.items():
            existing = document.get(section)
            if isinstance(existing, dict) and isinstance(change, dict):
                document[section] = {**existing, **change}
            else:
                document[section] = change
        return DisplayState.from_dict(document)

    def consume_fft(self) -> FFTFrame | None:
        frame = self._latest_fft
        self._latest_fft = None
        return frame

    def snapshot(self) -> StoreSnapshot:
        return StoreSnapshot(
            connected=self._connected,
            state=self._state,
            latest_fft=self._latest_fft,
            last_sequence=self._last_sequence,
            dropped_fft_frames=self._dropped_fft_frames,
            updated_monotonic=self._updated_monotonic,
        )
