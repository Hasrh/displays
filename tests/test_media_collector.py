"""Windows Global System Media Transport Controls collector tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pc.collectors.media import (
    MediaSessionSnapshot,
    WindowsMediaSessionCollector,
    datetime_from_winrt,
    interpolate_position,
    media_state_from_snapshot,
    timedelta_to_seconds,
)
from pc.collectors.system import SystemSample
from pc.state import HostStateSource
from shared.models import NetworkMetrics, SystemMetrics


def test_media_state_from_snapshot_idle() -> None:
    state = media_state_from_snapshot(None)
    assert state.title == ""
    assert state.artist == ""
    assert state.is_playing is False
    assert state.position_seconds == 0.0
    assert state.volume_percent is None


def test_interpolate_position_advances_while_playing() -> None:
    now = datetime(2026, 7, 30, 6, 0, 10, tzinfo=UTC)
    last_updated = datetime(2026, 7, 30, 6, 0, 0, tzinfo=UTC)
    position = interpolate_position(
        position_seconds=26.0,
        duration_seconds=259.0,
        is_playing=True,
        last_updated=last_updated,
        now=now,
    )
    assert position == 36.0


def test_interpolate_position_clamps_to_duration() -> None:
    now = datetime(2026, 7, 30, 6, 0, 30, tzinfo=UTC)
    last_updated = datetime(2026, 7, 30, 6, 0, 0, tzinfo=UTC)
    position = interpolate_position(
        position_seconds=250.0,
        duration_seconds=259.0,
        is_playing=True,
        last_updated=last_updated,
        now=now,
    )
    assert position == 259.0


def test_media_collector_maps_backend_snapshot() -> None:
    snapshot = MediaSessionSnapshot(
        title="Smile.mp3",
        artist="Demo Artist",
        album="Demo Album",
        is_playing=True,
        position_seconds=26.0,
        duration_seconds=259.0,
        last_updated=datetime(2026, 7, 30, 6, 0, 0, tzinfo=UTC),
        source_app_id="Spotify.exe",
    )

    class Backend:
        async def read_session(self) -> MediaSessionSnapshot | None:
            return snapshot

    collector = WindowsMediaSessionCollector(
        Backend(),
        clock=lambda: datetime(2026, 7, 30, 6, 0, 4, tzinfo=UTC),
    )
    state = asyncio.run(collector.sample())
    assert state.title == "Smile.mp3"
    assert state.artist == "Demo Artist"
    assert state.album == "Demo Album"
    assert state.is_playing is True
    assert state.position_seconds == 30.0
    assert state.duration_seconds == 259.0


def test_host_state_source_overlays_media_and_system() -> None:
    system = SystemSample(
        system=SystemMetrics(cpu_usage_percent=12.0, ram_usage_percent=40.0),
        network=NetworkMetrics(
            download_bytes_per_second=1_000.0,
            upload_bytes_per_second=200.0,
        ),
    )
    media = media_state_from_snapshot(
        MediaSessionSnapshot(
            title="Live Track",
            artist="Live Artist",
            album=None,
            is_playing=False,
            position_seconds=12.0,
            duration_seconds=100.0,
        )
    )

    class MediaBackend:
        async def sample(self):
            return media

    source = HostStateSource(
        system_collector=SimpleNamespace(sample=lambda: system),
        media_collector=MediaBackend(),
    )
    asyncio.run(source.initialize())
    state = source.state_at(3.0)
    assert state.system == system.system
    assert state.network == system.network
    assert state.media == media


def test_timedelta_helpers_accept_winrt_shaped_values() -> None:
    assert timedelta_to_seconds(timedelta(seconds=26, milliseconds=500)) == 26.5
    assert datetime_from_winrt(datetime(2026, 7, 30, 6, 0, 0)).tzinfo is UTC
