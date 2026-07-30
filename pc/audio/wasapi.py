"""WASAPI loopback capture that produces latest-value FFT frames."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import numpy as np

from pc.audio.fft import compute_fft_bins, mono_float32
from shared.constants import FFT_BIN_COUNT
from shared.models import FFTFrame

LOGGER = logging.getLogger(__name__)

try:
    import pyaudiowpatch as pyaudio  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - optional host dependency
    pyaudio = None


class LoopbackDevice(Protocol):
    @property
    def index(self) -> int: ...

    @property
    def name(self) -> str: ...

    @property
    def channels(self) -> int: ...

    @property
    def sample_rate(self) -> int: ...


class AudioBackend(Protocol):
    def open_loopback(self, *, frames_per_buffer: int) -> tuple[Any, LoopbackDevice]: ...

    def read(self, stream: Any, frames: int) -> bytes: ...

    def close(self, stream: Any) -> None: ...


class _DeviceInfo:
    __slots__ = ("channels", "index", "name", "sample_rate")

    def __init__(self, index: int, name: str, channels: int, sample_rate: int) -> None:
        self.index = index
        self.name = name
        self.channels = channels
        self.sample_rate = sample_rate


class PyAudioWPatchBackend:
    """Default Windows WASAPI loopback backend."""

    def __init__(self) -> None:
        if pyaudio is None:
            raise RuntimeError(
                "PyAudioWPatch is required for WASAPI loopback FFT; "
                'install with pip install -e ".[host]"'
            )
        self._manager: Any | None = None

    def open_loopback(self, *, frames_per_buffer: int) -> tuple[Any, LoopbackDevice]:
        manager = pyaudio.PyAudio()
        self._manager = manager
        try:
            device = self._select_loopback(manager)
        except (OSError, LookupError) as exc:
            manager.terminate()
            self._manager = None
            raise RuntimeError(f"WASAPI loopback device unavailable: {exc}") from exc

        info = _DeviceInfo(
            index=int(device["index"]),
            name=str(device["name"]),
            channels=max(1, int(device["maxInputChannels"])),
            sample_rate=int(device["defaultSampleRate"]),
        )
        stream = manager.open(
            format=pyaudio.paInt16,
            channels=info.channels,
            rate=info.sample_rate,
            input=True,
            input_device_index=info.index,
            frames_per_buffer=frames_per_buffer,
        )
        return stream, info

    def read(self, stream: Any, frames: int) -> bytes:
        return bytes(stream.read(frames, exception_on_overflow=False))

    def close(self, stream: Any) -> None:
        try:
            stream.stop_stream()
        except Exception:
            LOGGER.debug("WASAPI stream stop failed", exc_info=True)
        try:
            stream.close()
        except Exception:
            LOGGER.debug("WASAPI stream close failed", exc_info=True)
        if self._manager is not None:
            self._manager.terminate()
            self._manager = None

    def _select_loopback(self, manager: Any) -> dict[str, Any]:
        getter = getattr(manager, "get_default_wasapi_loopback", None)
        if callable(getter):
            try:
                return cast(dict[str, Any], getter())
            except (OSError, LookupError):
                pass
        return self._resolve_loopback(manager)

    @staticmethod
    def _resolve_loopback(manager: Any) -> dict[str, Any]:
        wasapi_info = manager.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = cast(
            dict[str, Any],
            manager.get_device_info_by_index(wasapi_info["defaultOutputDevice"]),
        )
        if speakers.get("isLoopbackDevice"):
            return speakers
        for loopback in manager.get_loopback_device_info_generator():
            candidate = cast(dict[str, Any], loopback)
            if speakers["name"] in candidate["name"]:
                return candidate
        raise LookupError("default WASAPI loopback device not found")


class WasapiLoopbackFftCollector:
    """Captures default speaker output and keeps the newest FFT frame."""

    def __init__(
        self,
        *,
        backend: AudioBackend | None = None,
        fft_size: int = 2048,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if fft_size < 64:
            raise ValueError("fft_size must be at least 64")
        self._backend = backend or PyAudioWPatchBackend()
        self._fft_size = fft_size
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: FFTFrame | None = None
        self._peak = 1e-3
        self._available: bool | None = None
        self.device_name: str | None = None

    @property
    def available(self) -> bool | None:
        return self._available

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="wasapi-loopback-fft",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8.0)
        self._thread = None

    def latest(self, captured_at: str | None = None) -> FFTFrame | None:
        with self._lock:
            frame = self._latest
        if frame is None:
            return None
        if captured_at is None:
            return frame
        return FFTFrame(captured_at=captured_at, bins=frame.bins)

    def _run(self) -> None:
        stream: Any | None = None
        try:
            stream, device = self._backend.open_loopback(frames_per_buffer=self._fft_size)
            self.device_name = device.name
            LOGGER.info("WASAPI loopback FFT opening device=%s", device.name)
            while not self._stop.is_set():
                raw = self._backend.read(stream, self._fft_size)
                samples = np.frombuffer(raw, dtype=np.int16)
                mono = mono_float32(samples, device.channels)
                if mono.size > self._fft_size:
                    mono = mono[: self._fft_size]
                elif mono.size < self._fft_size:
                    padded = np.zeros(self._fft_size, dtype=np.float32)
                    padded[: mono.size] = mono
                    mono = padded
                bins, self._peak = compute_fft_bins(mono, peak=self._peak)
                frame = FFTFrame(
                    captured_at=self._clock().isoformat().replace("+00:00", "Z"),
                    bins=bins if len(bins) == FFT_BIN_COUNT else bins[:FFT_BIN_COUNT],
                )
                with self._lock:
                    self._latest = frame
                if self._available is not True:
                    LOGGER.info("WASAPI loopback FFT active device=%s", device.name)
                    self._available = True
        except Exception:
            if self._available is not False:
                LOGGER.exception("WASAPI loopback FFT capture failed")
            self._available = False
        finally:
            if stream is not None:
                self._backend.close(stream)
