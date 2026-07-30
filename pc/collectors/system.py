"""Real Windows system telemetry with optional LibreHardwareMonitor sensors."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
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
_CPU_ID_PREFIXES = ("/intelcpu/", "/amdcpu/", "/cpu/")
_BOARD_ID_MARKERS = ("/lpc/", "/nct", "/it", "/asus", "/gigabyte", "/msi", "/board/")


@dataclass(frozen=True, slots=True)
class SystemSample:
    system: SystemMetrics
    network: NetworkMetrics


@dataclass(frozen=True, slots=True)
class HardwareSensors:
    gpus: tuple[GpuMetrics, ...] = ()
    cpu_temperature_c: float | None = None
    cpu_fan_rpm: float | None = None
    case_temperature_c: float | None = None
    case_fan_rpm: float | None = None


@dataclass(slots=True)
class _GpuAccumulator:
    name: str
    usage_values: list[float] = field(default_factory=list)
    memory_values: list[float] = field(default_factory=list)
    temperature_values: list[float] = field(default_factory=list)
    fan_values: list[float] = field(default_factory=list)


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


def _is_cpu_sensor(sensor_id: str) -> bool:
    lowered = sensor_id.lower()
    return any(lowered.startswith(prefix) for prefix in _CPU_ID_PREFIXES)


def _is_board_sensor(sensor_id: str) -> bool:
    lowered = sensor_id.lower()
    return any(marker in lowered for marker in _BOARD_ID_MARKERS)


def _prefer_temperature(text: str) -> int:
    lowered = text.lower()
    if "package" in lowered or "tctl" in lowered or "average" in lowered:
        return 0
    if "core" in lowered:
        return 1
    if "cpu" in lowered:
        return 2
    return 3


def _prefer_case_temperature(text: str) -> int:
    lowered = text.lower()
    if "system" in lowered or "ambient" in lowered or "case" in lowered or "motherboard" in lowered:
        return 0
    if "temp" in lowered:
        return 1
    return 2


def _prefer_fan(text: str, *, cpu: bool) -> int:
    lowered = text.lower()
    if cpu and "cpu" in lowered:
        return 0
    if not cpu and ("sys" in lowered or "chassis" in lowered or "case" in lowered):
        return 0
    if "fan" in lowered:
        return 1
    return 2


def parse_hardware_sensors(document: object) -> HardwareSensors:
    """Extract GPU, CPU, and board sensors without relying on unstable indexes."""

    if not isinstance(document, dict):
        raise ValueError("LibreHardwareMonitor document must be an object")
    accumulators: dict[str, _GpuAccumulator] = {}
    cpu_temperatures: list[tuple[int, float]] = []
    cpu_fans: list[tuple[int, float]] = []
    case_temperatures: list[tuple[int, float]] = []
    case_fans: list[tuple[int, float]] = []

    def visit(node: dict[str, Any], ancestors: tuple[str, ...]) -> None:
        sensor_id = node.get("SensorId")
        if isinstance(sensor_id, str):
            sensor_type = str(node.get("Type", "")).lower()
            text = str(node.get("Text", ""))
            text_lower = text.lower()
            value = _number(node.get("RawValue", node.get("Value")))
            if value is not None and sensor_id.startswith("/gpu-"):
                parts = sensor_id.split("/")
                if len(parts) >= 3:
                    prefix = f"/{parts[1]}/{parts[2]}"
                    accumulator = accumulators.setdefault(
                        prefix,
                        _GpuAccumulator(name=_gpu_name(ancestors, prefix)),
                    )
                    if sensor_type == "load" and "memory" in text_lower:
                        accumulator.memory_values.append(value)
                    elif sensor_type == "load" and (
                        "core" in text_lower or "3d" in text_lower or text_lower.strip() == "gpu"
                    ):
                        accumulator.usage_values.append(value)
                    elif sensor_type == "temperature" and (
                        "core" in text_lower or "gpu" in text_lower
                    ):
                        accumulator.temperature_values.append(value)
                    elif sensor_type in {"fan", "control"} and (
                        "fan" in text_lower or "gpu" in text_lower
                    ):
                        accumulator.fan_values.append(value)
            elif value is not None and _is_cpu_sensor(sensor_id):
                if sensor_type == "temperature":
                    cpu_temperatures.append((_prefer_temperature(text), value))
                elif sensor_type == "fan":
                    cpu_fans.append((_prefer_fan(text, cpu=True), value))
            elif value is not None and _is_board_sensor(sensor_id):
                if sensor_type == "temperature":
                    case_temperatures.append((_prefer_case_temperature(text), value))
                elif sensor_type == "fan":
                    if "cpu" in text_lower:
                        cpu_fans.append((_prefer_fan(text, cpu=True), value))
                    else:
                        case_fans.append((_prefer_fan(text, cpu=False), value))

        text_value = node.get("Text")
        next_ancestors = (*ancestors, text_value) if isinstance(text_value, str) else ancestors
        for child in _children(node):
            visit(child, next_ancestors)

    visit(document, ())
    gpus = tuple(
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
            fan_percent=(
                max(0.0, min(100.0, max(accumulator.fan_values)))
                if accumulator.fan_values
                else None
            ),
        )
        for _, accumulator in sorted(accumulators.items())
    )
    return HardwareSensors(
        gpus=gpus,
        cpu_temperature_c=min(cpu_temperatures)[1] if cpu_temperatures else None,
        cpu_fan_rpm=min(cpu_fans)[1] if cpu_fans else None,
        case_temperature_c=min(case_temperatures)[1] if case_temperatures else None,
        case_fan_rpm=min(case_fans)[1] if case_fans else None,
    )


def parse_gpu_metrics(document: object) -> tuple[GpuMetrics, ...]:
    """Extract every GPU without relying on unstable tree indexes."""

    return parse_hardware_sensors(document).gpus


class LibreHardwareMonitorClient:
    """Reads the optional local LibreHardwareMonitor web endpoint."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    def read_sensors(self) -> HardwareSensors:
        request = Request(self.url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            encoded = response.read(MAX_HARDWARE_DOCUMENT_BYTES + 1)
        if len(encoded) > MAX_HARDWARE_DOCUMENT_BYTES:
            raise ValueError("LibreHardwareMonitor response exceeds 2 MiB")
        document = json.loads(encoded)
        return parse_hardware_sensors(document)

    def read_gpus(self) -> tuple[GpuMetrics, ...]:
        return self.read_sensors().gpus


class WindowsSystemCollector:
    """Collects non-blocking psutil counters and optional hardware sensors."""

    def __init__(
        self,
        hardware_monitor: LibreHardwareMonitorClient | None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._hardware_monitor = hardware_monitor
        self._clock = clock
        self._last_network: tuple[int, int, float] | None = None
        self._last_sensors = HardwareSensors()
        self._hardware_available: bool | None = None

    def sample(self) -> SystemSample:
        cpu_usage = float(psutil.cpu_percent(interval=0.1))
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()
        disk_used_mb = self._disk_used_mb()
        now = self._clock()
        download_rate = 0.0
        upload_rate = 0.0
        if self._last_network is not None:
            previous_received, previous_sent, previous_time = self._last_network
            elapsed = max(0.001, now - previous_time)
            download_rate = max(0.0, (network.bytes_recv - previous_received) / elapsed)
            upload_rate = max(0.0, (network.bytes_sent - previous_sent) / elapsed)
        self._last_network = (network.bytes_recv, network.bytes_sent, now)

        sensors = self._read_sensors()
        gpus = sensors.gpus
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
                cpu_temperature_c=sensors.cpu_temperature_c,
                gpu_temperature_c=gpu_temperature,
                ram_used_mb=max(0.0, float(memory.used) / (1024.0 * 1024.0)),
                disk_used_mb=disk_used_mb,
                cpu_fan_rpm=sensors.cpu_fan_rpm,
                case_fan_rpm=sensors.case_fan_rpm,
                case_temperature_c=sensors.case_temperature_c,
                gpus=gpus,
            ),
            network=NetworkMetrics(
                download_bytes_per_second=download_rate,
                upload_bytes_per_second=upload_rate,
            ),
        )

    @staticmethod
    def _disk_used_mb() -> float | None:
        try:
            usage = psutil.disk_usage("C:\\")
        except OSError:
            return None
        return max(0.0, float(usage.used) / (1024.0 * 1024.0))

    def _read_sensors(self) -> HardwareSensors:
        if self._hardware_monitor is None:
            return HardwareSensors()
        try:
            sensors = self._hardware_monitor.read_sensors()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if self._hardware_available is not False:
                LOGGER.warning(
                    "LibreHardwareMonitor unavailable at %s: %s",
                    self._hardware_monitor.url,
                    exc,
                )
            self._hardware_available = False
            return self._last_sensors
        if self._hardware_available is not True:
            LOGGER.info(
                "LibreHardwareMonitor connected at %s GPUs=%d",
                self._hardware_monitor.url,
                len(sensors.gpus),
            )
        self._hardware_available = True
        self._last_sensors = sensors
        return sensors
