"""Windows Global System Media Transport Controls collector."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from shared.models import MediaState

LOGGER = logging.getLogger(__name__)

WinRTPlaybackStatus: Any
WinRTSessionManager: Any
WinRTBuffer: Any
WinRTInputStreamOptions: Any

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as WinRTSessionManager,
    )
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as WinRTPlaybackStatus,
    )
    from winrt.windows.storage.streams import Buffer as WinRTBuffer
    from winrt.windows.storage.streams import InputStreamOptions as WinRTInputStreamOptions
except ImportError:  # pragma: no cover - exercised on hosts without the optional extra
    WinRTPlaybackStatus = None
    WinRTSessionManager = None
    WinRTBuffer = None
    WinRTInputStreamOptions = None


class MediaSessionBackend(Protocol):
    async def read_session(self) -> MediaSessionSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class MediaSessionSnapshot:
    title: str
    artist: str
    album: str | None
    is_playing: bool
    position_seconds: float
    duration_seconds: float
    last_updated: datetime | None = None
    source_app_id: str | None = None
    thumbnail_bytes: bytes | None = None


@dataclass(frozen=True, slots=True)
class MediaSample:
    media: MediaState
    thumbnail_bytes: bytes | None = None


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_album(value: object) -> str | None:
    text = _coerce_text(value)
    return text or None


def timedelta_to_seconds(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, timedelta):
        return max(0.0, value.total_seconds())
    if isinstance(value, int | float):
        return max(0.0, float(value))
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        return max(0.0, float(total_seconds()))
    return 0.0


def datetime_from_winrt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return None


def interpolate_position(
    *,
    position_seconds: float,
    duration_seconds: float,
    is_playing: bool,
    last_updated: datetime | None,
    now: datetime,
) -> float:
    position = max(0.0, position_seconds)
    if duration_seconds > 0:
        position = min(position, duration_seconds)
    if not is_playing or last_updated is None:
        return position
    elapsed = max(0.0, (now - last_updated).total_seconds())
    interpolated = position + elapsed
    if duration_seconds > 0:
        return min(interpolated, duration_seconds)
    return interpolated


def album_art_id_for_bytes(image_bytes: bytes | None) -> str | None:
    if not image_bytes:
        return None
    return f"album-{hashlib.sha256(image_bytes).hexdigest()[:16]}"


def media_state_from_snapshot(
    snapshot: MediaSessionSnapshot | None,
    *,
    now: datetime | None = None,
) -> MediaState:
    if snapshot is None:
        return MediaState(
            title="",
            artist="",
            album=None,
            is_playing=False,
            position_seconds=0.0,
            duration_seconds=0.0,
            volume_percent=None,
            album_art_id=None,
        )
    clock = now or datetime.now(UTC)
    position = interpolate_position(
        position_seconds=snapshot.position_seconds,
        duration_seconds=snapshot.duration_seconds,
        is_playing=snapshot.is_playing,
        last_updated=snapshot.last_updated,
        now=clock,
    )
    return MediaState(
        title=snapshot.title,
        artist=snapshot.artist,
        album=snapshot.album,
        is_playing=snapshot.is_playing,
        position_seconds=position,
        duration_seconds=max(0.0, snapshot.duration_seconds),
        volume_percent=None,
        album_art_id=album_art_id_for_bytes(snapshot.thumbnail_bytes),
    )


def playback_is_active(status: object) -> bool:
    """Return True for GSMTC playing (and track-changing) sessions.

    GSMTC uses GlobalSystemMediaTransportControlsSessionPlaybackStatus, whose
    PLAYING value (4) differs from windows.media.MediaPlaybackStatus.PLAYING (3).
    """

    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.upper() in {"PLAYING", "CHANGING"}
    if WinRTPlaybackStatus is None:
        return False
    return status in {WinRTPlaybackStatus.PLAYING, WinRTPlaybackStatus.CHANGING}


async def read_thumbnail_bytes(thumbnail: object) -> bytes | None:
    if thumbnail is None or WinRTBuffer is None or WinRTInputStreamOptions is None:
        return None
    open_read = getattr(thumbnail, "open_read_async", None)
    if not callable(open_read):
        return None
    try:
        stream = await open_read()
        buffer = WinRTBuffer(2 * 1024 * 1024)
        await stream.read_async(buffer, buffer.capacity, WinRTInputStreamOptions.READ_AHEAD)
        data = bytes(buffer)
        return data or None
    except Exception:
        LOGGER.debug("Failed to read GSMTC thumbnail", exc_info=True)
        return None


class WinRTMediaSessionBackend:
    """Reads the current Windows media session through PyWinRT."""

    def __init__(
        self,
        manager_factory: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        if WinRTSessionManager is None:
            raise RuntimeError(
                "winrt-Windows.Media.Control is required for GSMTC collection; "
                'install with pip install -e ".[host]"'
            )
        self._manager_factory = manager_factory or WinRTSessionManager.request_async
        self._manager: Any | None = None

    async def read_session(self) -> MediaSessionSnapshot | None:
        if self._manager is None:
            self._manager = await self._manager_factory()
        session = self._manager.get_current_session()
        if session is None:
            sessions = list(self._manager.get_sessions())
            for candidate in sessions:
                playback = candidate.get_playback_info()
                if playback_is_active(playback.playback_status):
                    session = candidate
                    break
            if session is None and sessions:
                session = sessions[0]
        if session is None:
            return None

        properties = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        playback = session.get_playback_info()
        title = _coerce_text(None if properties is None else properties.title)
        artist = _coerce_text(None if properties is None else properties.artist)
        album = _optional_album(None if properties is None else properties.album_title)
        if not title and not artist:
            source = _coerce_text(session.source_app_user_model_id)
            title = source or "UNKNOWN MEDIA"
        thumbnail = None if properties is None else getattr(properties, "thumbnail", None)
        return MediaSessionSnapshot(
            title=title,
            artist=artist,
            album=album,
            is_playing=playback_is_active(playback.playback_status),
            position_seconds=timedelta_to_seconds(timeline.position),
            duration_seconds=timedelta_to_seconds(timeline.end_time),
            last_updated=datetime_from_winrt(timeline.last_updated_time),
            source_app_id=_optional_album(session.source_app_user_model_id),
            thumbnail_bytes=await read_thumbnail_bytes(thumbnail),
        )


class WindowsMediaSessionCollector:
    """Polls GSMTC and returns display-ready media samples."""

    def __init__(
        self,
        backend: MediaSessionBackend | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._backend = backend or WinRTMediaSessionBackend()
        self._clock = clock
        self._available: bool | None = None

    async def sample(self) -> MediaSample:
        try:
            snapshot = await self._backend.read_session()
        except Exception:
            if self._available is not False:
                LOGGER.exception("Windows media session collection failed")
            self._available = False
            return MediaSample(media=media_state_from_snapshot(None, now=self._clock()))
        if self._available is not True:
            LOGGER.info(
                "Windows media session collector is active session=%s",
                None if snapshot is None else snapshot.source_app_id or snapshot.title,
            )
        self._available = True
        return MediaSample(
            media=media_state_from_snapshot(snapshot, now=self._clock()),
            thumbnail_bytes=None if snapshot is None else snapshot.thumbnail_bytes,
        )
