"""Configuration parser tests."""

from pathlib import Path

import pytest

from pc.config import ConfigError as HostConfigError
from pc.config import load_config as load_host_config
from pi.config import ConfigError as PiConfigError
from pi.config import load_config as load_pi_config

ROOT = Path(__file__).resolve().parents[1]


def test_host_example_parses() -> None:
    config = load_host_config(ROOT / "config" / "host.example.toml")
    assert config.bind_host == "192.168.1.10"
    assert config.port == 8765
    assert config.log_level == "INFO"
    assert config.auth_token_env == "DESKTOP_DISPLAY_TOKEN"
    assert config.system_collector_enabled is True
    assert config.system_interval_seconds == 1.0
    assert config.hardware_monitor_enabled is True
    assert config.hardware_monitor_url == "http://127.0.0.1:8085/data.json"
    assert config.media_collector_enabled is True
    assert config.media_interval_seconds == 1.0
    assert config.fft_collector_enabled is True
    assert config.fft_size == 2048


def test_pi_example_parses() -> None:
    config = load_pi_config(ROOT / "config" / "pi.example.toml")
    assert config.host_url == "ws://192.168.1.10:8765"
    assert config.client_id == "display-pi"
    assert config.initial_page == "system"
    assert config.auto_cycle_seconds == 10.0
    assert (config.width, config.height) == (480, 320)
    assert config.display_backend == "framebuffer"
    assert config.framebuffer_device == Path("/dev/fb1")
    assert config.pixel_format == "rgb565"
    assert config.display_controller == "ili9486"
    assert config.touch_controller is None


def test_missing_host_config_fails_safely(tmp_path: Path) -> None:
    with pytest.raises(HostConfigError, match="not found"):
        load_host_config(tmp_path / "missing.toml")


def test_invalid_pi_orientation_fails(tmp_path: Path) -> None:
    path = tmp_path / "pi.toml"
    path.write_text(
        """
[application]
log_level = "INFO"
[host]
url = "ws://127.0.0.1:8765"
[display]
backend = "headless"
width = 320
height = 480
orientation = 45
target_fps = 25
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(PiConfigError, match="orientation"):
        load_pi_config(path)
