"""WASAPI loopback FFT helper and collector tests."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace

import numpy as np

from pc.audio.fft import compute_fft_bins, log_spaced_bins, mono_float32, normalize_bins
from pc.audio.wasapi import WasapiLoopbackFftCollector
from pc.state import HostStateSource
from shared.constants import FFT_BIN_COUNT
from shared.models import FFTFrame


def test_mono_float32_averages_stereo_channels() -> None:
    samples = np.array([1000, -1000, 2000, -2000], dtype=np.int16)
    mono = mono_float32(samples, channels=2)
    assert mono.shape == (2,)
    assert abs(float(mono[0])) < 1e-6
    assert abs(float(mono[1])) < 1e-6


def test_log_spaced_bins_preserve_count_and_range() -> None:
    magnitudes = np.linspace(0.0, 1.0, 513, dtype=np.float32)
    bins = log_spaced_bins(magnitudes, bin_count=FFT_BIN_COUNT)
    assert bins.shape == (FFT_BIN_COUNT,)
    assert float(bins.min()) >= 0.0
    assert float(bins.max()) <= 1.0


def test_compute_fft_bins_detects_sine_energy() -> None:
    rate = 48000
    frequency = 440.0
    samples = np.sin(2.0 * math.pi * frequency * np.arange(2048) / rate).astype(np.float32)
    bins, peak = compute_fft_bins(samples, peak=1e-3)
    assert len(bins) == FFT_BIN_COUNT
    assert peak > 1e-3
    assert max(bins) > 0.2


def test_normalize_bins_decays_peak() -> None:
    values = np.array([0.5, 0.25, 0.1], dtype=np.float32)
    normalized, peak = normalize_bins(values, peak=1.0, decay=0.5)
    assert peak == 0.5
    assert float(normalized.max()) <= 1.0


def test_wasapi_collector_publishes_latest_frame_from_backend() -> None:
    class Device:
        index = 0
        name = "Speakers [Loopback]"
        channels = 2
        sample_rate = 48000

    class Backend:
        def __init__(self) -> None:
            self.closed = False
            self.reads = 0

        def open_loopback(self, *, frames_per_buffer: int):
            del frames_per_buffer
            return object(), Device()

        def read(self, stream: object, frames: int) -> bytes:
            del stream
            self.reads += 1
            tone = np.sin(2.0 * math.pi * 880.0 * np.arange(frames) / 48000.0)
            stereo = np.column_stack((tone, tone)).astype(np.float32)
            pcm = (stereo.reshape(-1) * 16000).astype(np.int16)
            time.sleep(0.01)
            return pcm.tobytes()

        def close(self, stream: object) -> None:
            del stream
            self.closed = True

    backend = Backend()
    collector = WasapiLoopbackFftCollector(backend=backend, fft_size=512)
    collector.start()
    deadline = time.monotonic() + 2.0
    frame: FFTFrame | None = None
    while time.monotonic() < deadline:
        frame = collector.latest("2026-07-30T06:30:00Z")
        if frame is not None:
            break
        time.sleep(0.02)
    collector.stop()
    assert frame is not None
    assert len(frame.bins) == FFT_BIN_COUNT
    assert frame.captured_at == "2026-07-30T06:30:00Z"
    assert max(frame.bins) > 0.0
    assert backend.closed is True
    assert backend.reads >= 1


def test_host_state_source_prefers_live_fft_frames() -> None:
    live = FFTFrame(captured_at="ignored", bins=(0.8,) * FFT_BIN_COUNT)
    source = HostStateSource(
        fft_collector=SimpleNamespace(
            start=lambda: None,
            stop=lambda: None,
            latest=lambda captured_at=None: FFTFrame(
                captured_at=captured_at or live.captured_at,
                bins=live.bins,
            ),
        )
    )
    frame = source.fft_at(1.0, "2026-07-30T06:31:00Z")
    assert frame.bins[0] == 0.8
    assert frame.captured_at == "2026-07-30T06:31:00Z"
