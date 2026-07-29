"""Synthetic authoritative state used to verify the transport end to end."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic

from pc.collectors.system import SystemSample, WindowsSystemCollector
from shared.constants import FFT_BIN_COUNT
from shared.models import (
    ClockState,
    DisplayState,
    FFTFrame,
    GpuMetrics,
    MediaState,
    NetworkMetrics,
    SystemMetrics,
    WeatherState,
)

LOGGER = logging.getLogger(__name__)


class SyntheticStateSource:
    """Deterministic source that exercises every high-frequency transport path."""

    def state_at(self, elapsed_seconds: float) -> DisplayState:
        progress = elapsed_seconds % 240.0
        wave = (math.sin(elapsed_seconds * 0.7) + 1.0) / 2.0
        local_now = datetime.now().astimezone()
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
                gpus=(
                    GpuMetrics(
                        name="SYNTHETIC INTEGRATED GPU",
                        usage_percent=12.0 + wave * 25.0,
                    ),
                    GpuMetrics(
                        name="SYNTHETIC DISCRETE GPU",
                        usage_percent=20.0 + (1.0 - wave) * 50.0,
                    ),
                ),
            ),
            network=NetworkMetrics(
                download_bytes_per_second=250_000.0 + wave * 750_000.0,
                upload_bytes_per_second=25_000.0 + (1.0 - wave) * 125_000.0,
            ),
            weather=WeatherState(
                temperature_c=24.0,
                condition="SYNTHETIC CLEAR",
                observed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            ),
            clock=ClockState(
                time_text=local_now.strftime("%H:%M:%S"),
                date_text=local_now.strftime("%A %d %B"),
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


class HostStateSource(SyntheticStateSource):
    """Combines real system telemetry with synthetic not-yet-implemented sources."""

    def __init__(self, collector: WindowsSystemCollector, interval_seconds: float) -> None:
        self._collector = collector
        self._interval_seconds = interval_seconds
        self._latest_system: SystemSample | None = None
        self._collector_healthy: bool | None = None

    async def initialize(self) -> None:
        await self._collect_once()

    async def run(self) -> None:
        next_sample = monotonic() + self._interval_seconds
        while True:
            await asyncio.sleep(max(0.0, next_sample - monotonic()))
            await self._collect_once()
            next_sample += self._interval_seconds
            if next_sample < monotonic():
                next_sample = monotonic() + self._interval_seconds

    def state_at(self, elapsed_seconds: float) -> DisplayState:
        state = super().state_at(elapsed_seconds)
        if self._latest_system is None:
            return replace(state, system=None, network=None)
        return replace(
            state,
            system=self._latest_system.system,
            network=self._latest_system.network,
        )

    async def _collect_once(self) -> None:
        try:
            sample = await asyncio.to_thread(self._collector.sample)
        except Exception:
            if self._collector_healthy is not False:
                LOGGER.exception("Windows system telemetry collection failed")
            self._collector_healthy = False
            return
        if self._collector_healthy is not True:
            LOGGER.info("Windows system telemetry collector is active")
        self._collector_healthy = True
        self._latest_system = sample
