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
    auth_token_env: str
    heartbeat_interval_seconds: int
    client_timeout_seconds: int


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
    network_value = document.get("network", {})
    network = _table(network_value, "network")
    port = server.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("server.port must be an integer from 1 to 65535")

    log_level = _string(application, "log_level", "application").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("application.log_level is not a supported logging level")
    auth_token_env = network.get("auth_token_env", "DESKTOP_DISPLAY_TOKEN")
    if not isinstance(auth_token_env, str) or not auth_token_env.strip():
        raise ConfigError("network.auth_token_env must be a non-empty string")
    heartbeat_interval = _integer(
        network,
        "heartbeat_interval_seconds",
        "network",
        1,
        60,
        default=5,
    )
    client_timeout = _integer(
        network,
        "client_timeout_seconds",
        "network",
        3,
        300,
        default=15,
    )
    if client_timeout <= heartbeat_interval:
        raise ConfigError(
            "network.client_timeout_seconds must exceed heartbeat_interval_seconds"
        )

    return HostConfig(
        bind_host=_string(server, "bind_host", "server"),
        port=port,
        log_level=log_level,
        auth_token_env=auth_token_env,
        heartbeat_interval_seconds=heartbeat_interval,
        client_timeout_seconds=client_timeout,
    )
