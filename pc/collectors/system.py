"""Real Windows system telemetry with optional LibreHardwareMonitor GPUs."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.request import Request, urlopen

import psutil

from shared.models import GpuMetrics, NetworkMetrics, SystemMetrics

LOGGER = logging.getLogger(__name__)
MAX_HARDWARE_DOCUMENT_BYTES = 2 * 1024 * 1024
_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_SENSOR_GROUP_NAMES = {
    "clocks",
    "controls",
    "data",
    "factors",
    "fans",
    "levels",
    "load",
    "powers",
    "small data",
    "temperatures",
    "throughput",
    "voltages",
}


@dataclass(frozen=True, slots=True)
class SystemSample:
    system: SystemMetrics
    network: NetworkMetrics


@dataclass(slots=True)
class _GpuAccumulator:
    name: str
    usage_values: list[float]
    memory_values: list[float]
    temperature_values: list[float]


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _NUMBER_PATTERN.search(value)
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    raw = node.get("Children")
    if not isinstance(raw, list):
        return []
    return [child for child in raw if isinstance(child, dict)]


def _gpu_name(ancestors: tuple[str, ...], prefix: str) -> str:
    for name in reversed(ancestors):
        stripped = name.strip()
        if stripped and stripped.lower() not in _SENSOR_GROUP_NAMES:
            return stripped
    return prefix.removeprefix("/").replace("/", " ").upper()


def parse_gpu_metrics(document: object) -> tuple[GpuMetrics, ...]:
    """Extract every GPU without relying on unstable tree indexes."""

    if not isinstance(document, dict):
        raise ValueError("LibreHardwareMonitor document must be an object")
    accumulators: dict[str, _GpuAccumulator] = {}

    def visit(node: dict[str, Any], ancestors: tuple[str, ...]) -> None:
        sensor_id = node.get("SensorId")
        if isinstance(sensor_id, str) and sensor_id.startswith("/gpu-"):
            parts = sensor_id.split("/")
            if len(parts) >= 3:
                prefix = f"/{parts[1]}/{parts[2]}"
                accumulator = accumulators.setdefault(
                    prefix,
                    _GpuAccumulator(
                        name=_gpu_name(ancestors, prefix),
                        usage_values=[],
                        memory_values=[],
                        temperature_values=[],
                    ),
                )
                sensor_type = str(node.get("Type", "")).lower()
                text = str(node.get("Text", "")).lower()
                value = _number(node.get("RawValue", node.get("Value")))
                if value is not None:
                    if sensor_type == "load" and "memory" in text:
                        accumulator.memory_values.append(value)
                    elif sensor_type == "load" and (
                        "core" in text or "3d" in text or text.strip() == "gpu"
                    ):
                        accumulator.usage_values.append(value)
                    elif sensor_type == "temperature" and ("core" in text or "gpu" in text):
                        accumulator.temperature_values.append(value)

        text_value = node.get("Text")
        next_ancestors = (*ancestors, text_value) if isinstance(text_value, str) else ancestors
        for child in _children(node):
            visit(child, next_ancestors)

    visit(document, ())
    return tuple(
        GpuMetrics(
            name=accumulator.name,
            usage_percent=(
                max(0.0, min(100.0, max(accumulator.usage_values)))
                if accumulator.usage_values
                else None
            ),
            vram_usage_percent=(
                max(0.0, min(100.0, max(accumulator.memory_values)))
                if accumulator.memory_values
                else None
            ),
            temperature_c=(
                max(accumulator.temperature_values) if accumulator.temperature_values else None
            ),
        )
        for _, accumulator in sorted(accumulators.items())
    )


class LibreHardwareMonitorClient:
    """Reads the optional local LibreHardwareMonitor web endpoint."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    def read_gpus(self) -> tuple[GpuMetrics, ...]:
        request = Request(self.url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            encoded = response.read(MAX_HARDWARE_DOCUMENT_BYTES + 1)
        if len(encoded) > MAX_HARDWARE_DOCUMENT_BYTES:
            raise ValueError("LibreHardwareMonitor response exceeds 2 MiB")
        document = json.loads(encoded)
        return parse_gpu_metrics(document)


class WindowsSystemCollector:
    """Collects non-blocking psutil counters and optional per-GPU sensors."""

    def __init__(
        self,
        hardware_monitor: LibreHardwareMonitorClient | None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._hardware_monitor = hardware_monitor
        self._clock = clock
        self._last_network: tuple[int, int, float] | None = None
        self._last_gpus: tuple[GpuMetrics, ...] = ()
        self._hardware_available: bool | None = None

    def sample(self) -> SystemSample:
        cpu_usage = float(psutil.cpu_percent(interval=0.1))
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()
        now = self._clock()
        download_rate = 0.0
        upload_rate = 0.0
        if self._last_network is not None:
            previous_received, previous_sent, previous_time = self._last_network
            elapsed = max(0.001, now - previous_time)
            download_rate = max(0.0, (network.bytes_recv - previous_received) / elapsed)
            upload_rate = max(0.0, (network.bytes_sent - previous_sent) / elapsed)
        self._last_network = (network.bytes_recv, network.bytes_sent, now)

        gpus = self._read_gpus()
        gpu_usage = max(
            (gpu.usage_percent for gpu in gpus if gpu.usage_percent is not None),
            default=None,
        )
        vram_usage = max(
            (gpu.vram_usage_percent for gpu in gpus if gpu.vram_usage_percent is not None),
            default=None,
        )
        gpu_temperature = max(
            (gpu.temperature_c for gpu in gpus if gpu.temperature_c is not None),
            default=None,
        )
        return SystemSample(
            system=SystemMetrics(
                cpu_usage_percent=max(0.0, min(100.0, cpu_usage)),
                gpu_usage_percent=gpu_usage,
                ram_usage_percent=max(0.0, min(100.0, float(memory.percent))),
                vram_usage_percent=vram_usage,
                gpu_temperature_c=gpu_temperature,
                gpus=gpus,
            ),
            network=NetworkMetrics(
                download_bytes_per_second=download_rate,
                upload_bytes_per_second=upload_rate,
            ),
        )

    def _read_gpus(self) -> tuple[GpuMetrics, ...]:
        if self._hardware_monitor is None:
            return ()
        try:
            gpus = self._hardware_monitor.read_gpus()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if self._hardware_available is not False:
                LOGGER.warning(
                    "LibreHardwareMonitor unavailable at %s: %s",
                    self._hardware_monitor.url,
                    exc,
                )
            self._hardware_available = False
            return self._last_gpus
        if self._hardware_available is not True:
            LOGGER.info(
                "LibreHardwareMonitor connected at %s GPUs=%d",
                self._hardware_monitor.url,
                len(gpus),
            )
        self._hardware_available = True
        self._last_gpus = gpus
        return gpus
