"""Windows-side telemetry collectors."""

from pc.collectors.media import (
    MediaSessionSnapshot,
    WindowsMediaSessionCollector,
    interpolate_position,
    media_state_from_snapshot,
)
from pc.collectors.system import (
    LibreHardwareMonitorClient,
    SystemSample,
    WindowsSystemCollector,
    parse_gpu_metrics,
)

__all__ = [
    "LibreHardwareMonitorClient",
    "MediaSessionSnapshot",
    "SystemSample",
    "WindowsMediaSessionCollector",
    "WindowsSystemCollector",
    "interpolate_position",
    "media_state_from_snapshot",
    "parse_gpu_metrics",
]
