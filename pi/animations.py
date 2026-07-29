"""Frame-rate-independent smoothing for renderer values."""

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
