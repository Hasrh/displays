"""Typed host configuration loading and validation."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class HostConfig:
    bind_host: str
    port: int
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


def load_config(path: Path) -> HostConfig:
    """Load a host TOML file without resolving or logging secrets."""

    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    server = _table(document.get("server"), "server")
    application = _table(document.get("application"), "application")
    port = server.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("server.port must be an integer from 1 to 65535")

    log_level = _string(application, "log_level", "application").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("application.log_level is not a supported logging level")

    return HostConfig(
        bind_host=_string(server, "bind_host", "server"),
        port=port,
        log_level=log_level,
    )
