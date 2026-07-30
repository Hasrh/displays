"""Windows system and LibreHardwareMonitor collector tests."""

import asyncio
from types import SimpleNamespace

from pc.collectors import system as system_module
from pc.collectors.system import (
    HardwareSensors,
    SystemSample,
    WindowsSystemCollector,
    parse_gpu_metrics,
    parse_hardware_sensors,
)
from pc.state import HostStateSource
from shared.models import GpuMetrics, NetworkMetrics, SystemMetrics


def sensor(
    sensor_id: str,
    sensor_type: str,
    text: str,
    value: str,
) -> dict[str, object]:
    return {
        "SensorId": sensor_id,
        "Type": sensor_type,
        "Text": text,
        "RawValue": value,
        "Children": [],
    }


def test_parse_gpu_metrics_discovers_both_gpus_by_sensor_id() -> None:
    document = {
        "Text": "Root",
        "Children": [
            {
                "Text": "DESKTOP",
                "Children": [
                    {
                        "Text": "Intel Iris Xe Graphics",
                        "Children": [
                            {
                                "Text": "Load",
                                "Children": [
                                    sensor("/gpu-intel/0/load/0", "Load", "D3D 3D", "37,5 %"),
                                    sensor(
                                        "/gpu-intel/0/load/1",
                                        "Load",
                                        "GPU Memory",
                                        "22.0 %",
                                    ),
                                ],
                            }
                        ],
                    },
                    {
                        "Text": "NVIDIA GeForce RTX 4060",
                        "Children": [
                            {
                                "Text": "Load",
                                "Children": [
                                    sensor("/gpu-nvidia/0/load/0", "Load", "GPU Core", "71.2 %")
                                ],
                            },
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    sensor(
                                        "/gpu-nvidia/0/temperature/0",
                                        "Temperature",
                                        "GPU Core",
                                        "63.0 °C",
                                    )
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }

    gpus = parse_gpu_metrics(document)
    assert [gpu.name for gpu in gpus] == [
        "Intel Iris Xe Graphics",
        "NVIDIA GeForce RTX 4060",
    ]
    assert gpus[0].usage_percent == 37.5
    assert gpus[0].vram_usage_percent == 22.0
    assert gpus[1].usage_percent == 71.2
    assert gpus[1].temperature_c == 63.0


def test_parse_hardware_sensors_reads_cpu_gpu_and_case() -> None:
    document = {
        "Text": "Root",
        "Children": [
            {
                "Text": "DESKTOP",
                "Children": [
                    {
                        "Text": "Intel Core",
                        "Children": [
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    sensor(
                                        "/intelcpu/0/temperature/0",
                                        "Temperature",
                                        "CPU Package",
                                        "40.0 °C",
                                    )
                                ],
                            }
                        ],
                    },
                    {
                        "Text": "Nuvoton NCT6798D",
                        "Children": [
                            {
                                "Text": "Fans",
                                "Children": [
                                    sensor("/lpc/nct6798d/fan/0", "Fan", "CPU Fan", "874"),
                                    sensor("/lpc/nct6798d/fan/1", "Fan", "System Fan", "906"),
                                ],
                            },
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    sensor(
                                        "/lpc/nct6798d/temperature/0",
                                        "Temperature",
                                        "System",
                                        "34.0 °C",
                                    )
                                ],
                            },
                        ],
                    },
                    {
                        "Text": "NVIDIA GeForce RTX 4060",
                        "Children": [
                            {
                                "Text": "Load",
                                "Children": [
                                    sensor("/gpu-nvidia/0/load/0", "Load", "GPU Core", "71.2 %")
                                ],
                            },
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    sensor(
                                        "/gpu-nvidia/0/temperature/0",
                                        "Temperature",
                                        "GPU Core",
                                        "65.0 °C",
                                    )
                                ],
                            },
                            {
                                "Text": "Controls",
                                "Children": [
                                    sensor("/gpu-nvidia/0/control/0", "Control", "GPU Fan", "50 %")
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }

    sensors = parse_hardware_sensors(document)
    assert sensors.cpu_temperature_c == 40.0
    assert sensors.cpu_fan_rpm == 874.0
    assert sensors.case_fan_rpm == 906.0
    assert sensors.case_temperature_c == 34.0
    assert sensors.gpus[0].temperature_c == 65.0
    assert sensors.gpus[0].fan_percent == 50.0


def test_system_collector_calculates_network_rates(monkeypatch: object) -> None:
    times = iter((10.0, 12.0))
    counters = iter(
        (
            SimpleNamespace(bytes_recv=1_000, bytes_sent=500),
            SimpleNamespace(bytes_recv=5_000, bytes_sent=1_500),
        )
    )
    monkeypatch.setattr(system_module.psutil, "cpu_percent", lambda interval=None: 42.0)
    monkeypatch.setattr(
        system_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=61.0, used=3_204 * 1024 * 1024),
    )
    monkeypatch.setattr(
        system_module.psutil,
        "disk_usage",
        lambda _path: SimpleNamespace(used=980 * 1024 * 1024),
    )
    monkeypatch.setattr(system_module.psutil, "net_io_counters", lambda: next(counters))

    collector = WindowsSystemCollector(None, clock=lambda: next(times))
    first = collector.sample()
    second = collector.sample()

    assert first.network.download_bytes_per_second == 0.0
    assert second.network.download_bytes_per_second == 2_000.0
    assert second.network.upload_bytes_per_second == 500.0
    assert second.system.cpu_usage_percent == 42.0
    assert second.system.ram_usage_percent == 61.0
    assert second.system.ram_used_mb == 3204.0
    assert second.system.disk_used_mb == 980.0


def test_host_state_source_overlays_real_system_data() -> None:
    expected = SystemSample(
        system=SystemMetrics(cpu_usage_percent=52.0, ram_usage_percent=63.0),
        network=NetworkMetrics(
            download_bytes_per_second=12_000.0,
            upload_bytes_per_second=2_000.0,
        ),
    )
    collector = SimpleNamespace(sample=lambda: expected)
    source = HostStateSource(system_collector=collector, system_interval_seconds=1.0)
    asyncio.run(source.initialize())

    state = source.state_at(5.0)
    assert state.system == expected.system
    assert state.network == expected.network
    assert state.media is not None
    assert state.media.title == "Desktop Display Network Test"


def test_collector_retains_last_gpu_sample_during_outage(monkeypatch: object) -> None:
    class IntermittentMonitor:
        url = "http://127.0.0.1:8085/data.json"

        def __init__(self) -> None:
            self.calls = 0

        def read_sensors(self) -> HardwareSensors:
            self.calls += 1
            if self.calls > 1:
                raise OSError("temporary outage")
            return HardwareSensors(gpus=(GpuMetrics(name="Discrete GPU", usage_percent=64.0),))

    monkeypatch.setattr(system_module.psutil, "cpu_percent", lambda interval=None: 10.0)
    monkeypatch.setattr(
        system_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=20.0, used=1024 * 1024 * 1024),
    )
    monkeypatch.setattr(
        system_module.psutil,
        "disk_usage",
        lambda _path: SimpleNamespace(used=2 * 1024 * 1024 * 1024),
    )
    monkeypatch.setattr(
        system_module.psutil,
        "net_io_counters",
        lambda: SimpleNamespace(bytes_recv=1_000, bytes_sent=500),
    )
    monitor = IntermittentMonitor()
    collector = WindowsSystemCollector(monitor, clock=lambda: 1.0)

    assert collector.sample().system.gpus[0].usage_percent == 64.0
    assert collector.sample().system.gpus[0].usage_percent == 64.0
