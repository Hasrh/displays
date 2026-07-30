"""Frame-rate-independent smoothing and lightweight display animations."""

from __future__ import annotations

import math
from collections.abc import Sequence


class SmoothedBins:
    """Attack/release smoothing that never owns transport history."""

    def __init__(
        self,
        count: int,
        *,
        attack_rate: float = 18.0,
        release_rate: float = 7.0,
    ) -> None:
        if count <= 0 or attack_rate <= 0 or release_rate <= 0:
            raise ValueError("smoothing parameters must be positive")
        self.values = [0.0] * count
        self.attack_rate = attack_rate
        self.release_rate = release_rate

    def update(self, target: Sequence[float] | None, delta_seconds: float) -> tuple[float, ...]:
        delta = max(0.0, min(delta_seconds, 0.25))
        for index, current in enumerate(self.values):
            desired = target[index] if target is not None and index < len(target) else 0.0
            desired = max(0.0, min(1.0, float(desired)))
            rate = self.attack_rate if desired > current else self.release_rate
            blend = 1.0 - math.exp(-rate * delta)
            self.values[index] = current + (desired - current) * blend
        return tuple(self.values)


class ProgressPulse:
    """Subtle brightness pulse for the Now Playing progress bar."""

    def __init__(self, *, frequency_hz: float = 0.7, amplitude: float = 0.18) -> None:
        if frequency_hz <= 0 or amplitude < 0:
            raise ValueError("progress pulse parameters must be non-negative / positive")
        self.frequency_hz = frequency_hz
        self.amplitude = amplitude
        self._elapsed = 0.0

    def update(self, delta_seconds: float, *, active: bool) -> float:
        if not active:
            self._elapsed = 0.0
            return 1.0
        self._elapsed += max(0.0, delta_seconds)
        wave = 0.5 + 0.5 * math.sin(self._elapsed * self.frequency_hz * math.tau)
        return 1.0 - self.amplitude + self.amplitude * wave


class PageTransition:
    """Short ease-out cover used when the selected page changes."""

    def __init__(self, *, duration_seconds: float = 0.28) -> None:
        if duration_seconds <= 0:
            raise ValueError("page transition duration must be positive")
        self.duration_seconds = duration_seconds
        self._elapsed = duration_seconds
        self._last_revision = -1

    def observe(self, page_revision: int) -> None:
        if page_revision != self._last_revision:
            if self._last_revision >= 0:
                self._elapsed = 0.0
            self._last_revision = page_revision

    def update(self, delta_seconds: float) -> float:
        self._elapsed = min(self.duration_seconds, self._elapsed + max(0.0, delta_seconds))
        progress = self._elapsed / self.duration_seconds
        # Ease-out cubic keeps the wipe short on the Pi Zero.
        return 1.0 - (1.0 - progress) ** 3

    @property
    def active(self) -> bool:
        return self._elapsed < self.duration_seconds


def mix_rgb(
    color: tuple[int, int, int],
    other: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    blend = max(0.0, min(1.0, amount))
    return (
        int(color[0] + (other[0] - color[0]) * blend),
        int(color[1] + (other[1] - color[1]) * blend),
        int(color[2] + (other[2] - color[2]) * blend),
    )


def scale_rgb(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, factor))
    return (
        min(255, int(color[0] * amount)),
        min(255, int(color[1] * amount)),
        min(255, int(color[2] * amount)),
    )
