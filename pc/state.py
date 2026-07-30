"""Authoritative host state composition for synthetic and live collectors."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol

from pc.assets import PreparedAlbumArt, prepare_album_art
from pc.collectors.media import MediaSample
from pc.collectors.system import SystemSample
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


class SystemCollector(Protocol):
    def sample(self) -> SystemSample: ...


class MediaCollector(Protocol):
    async def sample(self) -> MediaSample: ...


class FftCollector(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def latest(self, captured_at: str | None = None) -> FFTFrame | None: ...


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
                ram_used_mb=3204.0 + wave * 200.0,
                disk_used_mb=980.0,
                cpu_fan_rpm=800.0 + wave * 200.0,
                case_fan_rpm=900.0 + wave * 80.0,
                case_temperature_c=34.0 + wave * 2.0,
                gpus=(
                    GpuMetrics(
                        name="SYNTHETIC INTEGRATED GPU",
                        usage_percent=12.0 + wave * 25.0,
                        temperature_c=45.0 + wave * 5.0,
                        fan_percent=35.0 + wave * 20.0,
                    ),
                    GpuMetrics(
                        name="SYNTHETIC DISCRETE GPU",
                        usage_percent=20.0 + (1.0 - wave) * 50.0,
                        temperature_c=52.0 + wave * 7.0,
                        fan_percent=50.0 + wave * 25.0,
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

    def take_asset(self) -> PreparedAlbumArt | None:
        return None


class HostStateSource(SyntheticStateSource):
    """Overlays live collectors onto unfinished synthetic sources."""

    def __init__(
        self,
        *,
        system_collector: SystemCollector | None = None,
        system_interval_seconds: float = 1.0,
        media_collector: MediaCollector | None = None,
        media_interval_seconds: float = 1.0,
        fft_collector: FftCollector | None = None,
        album_art_enabled: bool = True,
    ) -> None:
        self._system_collector = system_collector
        self._system_interval_seconds = system_interval_seconds
        self._media_collector = media_collector
        self._media_interval_seconds = media_interval_seconds
        self._fft_collector = fft_collector
        self._album_art_enabled = album_art_enabled
        self._latest_system: SystemSample | None = None
        self._latest_media: MediaState | None = None
        self._system_healthy: bool | None = None
        self._media_healthy: bool | None = None
        self._prepared_art: PreparedAlbumArt | None = None
        self._pending_art: PreparedAlbumArt | None = None
        self._last_thumbnail_id: str | None = None

    async def initialize(self) -> None:
        if self._fft_collector is not None:
            self._fft_collector.start()
        tasks: list[Awaitable[None]] = []
        if self._system_collector is not None:
            tasks.append(self._collect_system_once())
        if self._media_collector is not None:
            tasks.append(self._collect_media_once())
        if tasks:
            await asyncio.gather(*tasks)

    async def run(self) -> None:
        tasks: list[asyncio.Task[None]] = []
        if self._system_collector is not None:
            tasks.append(
                asyncio.create_task(
                    self._poll(
                        self._collect_system_once,
                        self._system_interval_seconds,
                    ),
                    name="windows-system-collector",
                )
            )
        if self._media_collector is not None:
            tasks.append(
                asyncio.create_task(
                    self._poll(
                        self._collect_media_once,
                        self._media_interval_seconds,
                    ),
                    name="windows-media-collector",
                )
            )
        try:
            if not tasks:
                await asyncio.Event().wait()
                return
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        finally:
            if self._fft_collector is not None:
                self._fft_collector.stop()

    def state_at(self, elapsed_seconds: float) -> DisplayState:
        state = super().state_at(elapsed_seconds)
        if self._system_collector is not None:
            if self._latest_system is None:
                state = replace(state, system=None, network=None)
            else:
                state = replace(
                    state,
                    system=self._latest_system.system,
                    network=self._latest_system.network,
                )
        if self._media_collector is not None:
            state = replace(state, media=self._latest_media)
        return state

    def fft_at(self, elapsed_seconds: float, captured_at: str) -> FFTFrame:
        if self._fft_collector is not None:
            frame = self._fft_collector.latest(captured_at)
            if frame is not None:
                return frame
        return super().fft_at(elapsed_seconds, captured_at)

    def take_asset(self) -> PreparedAlbumArt | None:
        asset = self._pending_art
        self._pending_art = None
        return asset

    async def _poll(
        self,
        collect: Callable[[], Awaitable[None]],
        interval_seconds: float,
    ) -> None:
        next_sample = monotonic() + interval_seconds
        while True:
            await asyncio.sleep(max(0.0, next_sample - monotonic()))
            await collect()
            next_sample += interval_seconds
            if next_sample < monotonic():
                next_sample = monotonic() + interval_seconds

    async def _collect_system_once(self) -> None:
        assert self._system_collector is not None
        try:
            sample = await asyncio.to_thread(self._system_collector.sample)
        except Exception:
            if self._system_healthy is not False:
                LOGGER.exception("Windows system telemetry collection failed")
            self._system_healthy = False
            return
        if self._system_healthy is not True:
            LOGGER.info("Windows system telemetry collector is active")
        self._system_healthy = True
        self._latest_system = sample

    async def _collect_media_once(self) -> None:
        assert self._media_collector is not None
        try:
            sample = await self._media_collector.sample()
        except Exception:
            if self._media_healthy is not False:
                LOGGER.exception("Windows media session collection failed")
            self._media_healthy = False
            return
        if self._media_healthy is not True:
            LOGGER.info("Windows media session collector is active")
        self._media_healthy = True
        self._latest_media = sample.media
        await self._maybe_prepare_album_art(sample)

    async def _maybe_prepare_album_art(self, sample: MediaSample) -> None:
        if not self._album_art_enabled:
            return
        thumbnail_id = sample.media.album_art_id
        if thumbnail_id is None or sample.thumbnail_bytes is None:
            return
        if thumbnail_id == self._last_thumbnail_id and self._prepared_art is not None:
            prepared_id = self._prepared_art.metadata.asset_id
            if sample.media.album_art_id != prepared_id:
                self._latest_media = replace(sample.media, album_art_id=prepared_id)
            return
        try:
            prepared = await asyncio.to_thread(prepare_album_art, sample.thumbnail_bytes)
        except Exception:
            LOGGER.exception("Album art preparation failed")
            return
        self._prepared_art = prepared
        self._pending_art = prepared
        self._last_thumbnail_id = thumbnail_id
        self._latest_media = replace(sample.media, album_art_id=prepared.metadata.asset_id)
        LOGGER.info(
            "Prepared album art id=%s bytes=%d",
            prepared.metadata.asset_id,
            prepared.metadata.byte_length,
        )
