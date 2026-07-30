"""NumPy FFT helpers shared by the WASAPI loopback analyzer."""

from __future__ import annotations

import math
from typing import cast

import numpy as np
from numpy.typing import NDArray

from shared.constants import FFT_BIN_COUNT


def mono_float32(
    samples: NDArray[np.floating] | NDArray[np.integer], channels: int
) -> NDArray[np.float32]:
    """Convert interleaved PCM samples into a mono float32 waveform."""

    array = np.asarray(samples)
    if array.size == 0:
        return np.zeros(0, dtype=np.float32)
    if np.issubdtype(array.dtype, np.integer):
        max_value = float(np.iinfo(array.dtype).max)
        array = array.astype(np.float32) / max_value
    else:
        array = array.astype(np.float32, copy=False)
    if channels <= 1:
        return cast(NDArray[np.float32], array.reshape(-1))
    framed = array.reshape(-1, channels)
    return cast(NDArray[np.float32], framed.mean(axis=1))


def log_spaced_bins(
    magnitudes: NDArray[np.floating],
    *,
    bin_count: int = FFT_BIN_COUNT,
) -> NDArray[np.float32]:
    """Collapse a linear magnitude spectrum into log-spaced display bins."""

    if bin_count <= 0:
        raise ValueError("bin_count must be positive")
    if magnitudes.size == 0:
        return np.zeros(bin_count, dtype=np.float32)

    spectrum = np.asarray(magnitudes, dtype=np.float32)
    usable = max(1, spectrum.size - 1)
    edges = np.geomspace(1.0, float(usable), num=bin_count + 1)
    bins = np.zeros(bin_count, dtype=np.float32)
    for index in range(bin_count):
        start = math.floor(edges[index])
        end = math.ceil(edges[index + 1])
        start = max(1, min(start, usable))
        end = max(start + 1, min(end, spectrum.size))
        bins[index] = float(np.mean(spectrum[start:end]))
    return bins


def normalize_bins(
    bins: NDArray[np.floating],
    *,
    peak: float,
    floor: float = 1e-5,
    decay: float = 0.92,
) -> tuple[NDArray[np.float32], float]:
    """Peak-normalize bins with a slow-decaying reference level."""

    values = np.asarray(bins, dtype=np.float32)
    current = float(np.max(values)) if values.size else 0.0
    updated_peak = max(floor, current, peak * decay)
    scaled = np.clip(values / updated_peak, 0.0, 1.0)
    # Mild perceptual lift so quiet material still reads on the display.
    lifted = np.power(scaled, 0.65, dtype=np.float32)
    return lifted, updated_peak


def compute_fft_bins(
    mono_samples: NDArray[np.floating],
    *,
    peak: float,
    bin_count: int = FFT_BIN_COUNT,
) -> tuple[tuple[float, ...], float]:
    """Window a mono buffer and return normalized display bins plus the new peak."""

    samples = np.asarray(mono_samples, dtype=np.float32)
    if samples.size < 16:
        empty = tuple(0.0 for _ in range(bin_count))
        return empty, max(peak * 0.92, 1e-5)

    window = np.hanning(samples.size).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples * window))
    bins = log_spaced_bins(spectrum, bin_count=bin_count)
    normalized, updated_peak = normalize_bins(bins, peak=peak)
    return tuple(float(value) for value in normalized), updated_peak
