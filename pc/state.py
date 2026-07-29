"""Synthetic authoritative state used to verify the transport end to end."""

from __future__ import annotations

import math

from shared.constants import FFT_BIN_COUNT
from shared.models import DisplayState, FFTFrame, MediaState, NetworkMetrics, SystemMetrics


class SyntheticStateSource:
    """Deterministic source that exercises every high-frequency transport path."""

    def state_at(self, elapsed_seconds: float) -> DisplayState:
        progress = elapsed_seconds % 240.0
        wave = (math.sin(elapsed_seconds * 0.7) + 1.0) / 2.0
        return DisplayState(
            media=MediaState(
                title="Desktop Display Network Test",
                artist="Synthetic Source",
                album="Transport Validation",
                is_playing=True,
                position_seconds=progress,
                duration_seconds=240.0,
                volume_percent=65.0,
            ),
            system=SystemMetrics(
                cpu_usage_percent=15.0 + wave * 55.0,
                gpu_usage_percent=20.0 + (1.0 - wave) * 50.0,
                ram_usage_percent=42.0,
                vram_usage_percent=35.0,
                cpu_temperature_c=48.0 + wave * 8.0,
                gpu_temperature_c=52.0 + wave * 7.0,
            ),
            network=NetworkMetrics(
                download_bytes_per_second=250_000.0 + wave * 750_000.0,
                upload_bytes_per_second=25_000.0 + (1.0 - wave) * 125_000.0,
            ),
        )

    def fft_at(self, elapsed_seconds: float, captured_at: str) -> FFTFrame:
        bins = tuple(
            max(
                0.0,
                min(
                    1.0,
                    0.12
                    + 0.7
                    * abs(
                        math.sin(elapsed_seconds * 4.0 + index * 0.31)
                        * math.sin(index * 0.09 + elapsed_seconds)
                    ),
                ),
            )
            for index in range(FFT_BIN_COUNT)
        )
        return FFTFrame(captured_at=captured_at, bins=bins)
