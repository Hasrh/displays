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


def _integer(table: dict[str, Any], key: str, section: str, minimum: int, maximum: int) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ConfigError(f"{section}.{key} must be an integer from {minimum} to {maximum}")
    return value


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

    return PiConfig(
        host_url=_string(host, "url", "host"),
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
