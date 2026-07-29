"""Typed Raspberry Pi configuration loading and validation."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class PiConfig:
    host_url: str
    client_id: str
    auth_token_env: str
    reconnect_initial_seconds: float
    reconnect_max_seconds: float
    handshake_timeout_seconds: int
    initial_page: str
    auto_cycle_seconds: float
    width: int
    height: int
    orientation: int
    target_fps: int
    display_backend: str
    framebuffer_device: Path
    pixel_format: Literal["rgb565"]
    display_controller: str
    touch_controller: str | None
    log_level: str


def _table(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a TOML table")
    return value


def _string(table: dict[str, Any], key: str, section: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string")
    return value


def _integer(
    table: dict[str, Any],
    key: str,
    section: str,
    minimum: int,
    maximum: int,
    *,
    default: int | None = None,
) -> int:
    value = table.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ConfigError(f"{section}.{key} must be an integer from {minimum} to {maximum}")
    return value


def _number(
    table: dict[str, Any],
    key: str,
    section: str,
    minimum: float,
    maximum: float,
    *,
    default: float,
) -> float:
    value = table.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= float(value) <= maximum
    ):
        raise ConfigError(f"{section}.{key} must be a number from {minimum} to {maximum}")
    return float(value)


def load_config(path: Path) -> PiConfig:
    """Load and validate Pi settings without touching display or input devices."""

    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    host = _table(document.get("host"), "host")
    display = _table(document.get("display"), "display")
    application = _table(document.get("application"), "application")
    network = _table(document.get("network", {}), "network")
    navigation = _table(document.get("navigation", {}), "navigation")

    orientation = _integer(display, "orientation", "display", 0, 270)
    if orientation not in {0, 90, 180, 270}:
        raise ConfigError("display.orientation must be one of 0, 90, 180, or 270")

    backend = _string(display, "backend", "display")
    if backend not in {"auto", "kmsdrm", "framebuffer", "headless"}:
        raise ConfigError("display.backend must be auto, kmsdrm, framebuffer, or headless")

    display_controller = _string(display, "controller", "display").lower()
    if display_controller not in {"ili9486"}:
        raise ConfigError("display.controller must be ili9486")

    touch_value = document.get("touch")
    touch_controller: str | None = None
    if touch_value is not None:
        touch = _table(touch_value, "touch")
        touch_controller = _string(touch, "controller", "touch").lower()
        if touch_controller not in {"xpt2046"}:
            raise ConfigError("touch.controller must be xpt2046")

    pixel_format = _string(display, "pixel_format", "display").lower()
    if pixel_format != "rgb565":
        raise ConfigError("display.pixel_format must be rgb565")

    log_level = _string(application, "log_level", "application").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("application.log_level is not a supported logging level")
    client_id = network.get("client_id", "display-pi")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ConfigError("network.client_id must be a non-empty string")
    auth_token_env = network.get("auth_token_env", "DESKTOP_DISPLAY_TOKEN")
    if not isinstance(auth_token_env, str) or not auth_token_env.strip():
        raise ConfigError("network.auth_token_env must be a non-empty string")
    reconnect_initial = _number(
        network,
        "reconnect_initial_seconds",
        "network",
        0.1,
        60.0,
        default=1.0,
    )
    reconnect_max = _number(
        network,
        "reconnect_max_seconds",
        "network",
        1.0,
        300.0,
        default=30.0,
    )
    if reconnect_max < reconnect_initial:
        raise ConfigError(
            "network.reconnect_max_seconds must be at least reconnect_initial_seconds"
        )
    initial_page = navigation.get("initial_page", "system")
    if not isinstance(initial_page, str) or initial_page not in {
        "now_playing",
        "visualizer",
        "system",
        "clock",
    }:
        raise ConfigError(
            "navigation.initial_page must be now_playing, visualizer, system, or clock"
        )
    auto_cycle_seconds = _number(
        navigation,
        "auto_cycle_seconds",
        "navigation",
        0.0,
        3600.0,
        default=10.0,
    )

    return PiConfig(
        host_url=_string(host, "url", "host"),
        client_id=client_id,
        auth_token_env=auth_token_env,
        reconnect_initial_seconds=reconnect_initial,
        reconnect_max_seconds=reconnect_max,
        handshake_timeout_seconds=_integer(
            network,
            "handshake_timeout_seconds",
            "network",
            1,
            60,
            default=10,
        ),
        initial_page=initial_page,
        auto_cycle_seconds=auto_cycle_seconds,
        width=_integer(display, "width", "display", 1, 8192),
        height=_integer(display, "height", "display", 1, 8192),
        orientation=orientation,
        target_fps=_integer(display, "target_fps", "display", 1, 120),
        display_backend=backend,
        framebuffer_device=Path(_string(display, "device", "display")),
        pixel_format="rgb565",
        display_controller=display_controller,
        touch_controller=touch_controller,
        log_level=log_level,
    )
