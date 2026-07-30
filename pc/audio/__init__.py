"""Host-side audio capture and FFT processing."""

from pc.audio.fft import compute_fft_bins, log_spaced_bins, mono_float32, normalize_bins
from pc.audio.wasapi import WasapiLoopbackFftCollector

__all__ = [
    "WasapiLoopbackFftCollector",
    "compute_fft_bins",
    "log_spaced_bins",
    "mono_float32",
    "normalize_bins",
]
