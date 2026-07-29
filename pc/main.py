"""Windows host composition root."""

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from pc.collectors import LibreHardwareMonitorClient, WindowsSystemCollector
from pc.config import ConfigError, HostConfig, load_config
from pc.network import StateSource, WebSocketHost
from pc.state import HostStateSource, SyntheticStateSource

LOGGER = logging.getLogger(__name__)


async def run_application(config: HostConfig, auth_token: str) -> None:
    source: StateSource
    collector_task: asyncio.Task[None] | None = None
    if config.system_collector_enabled:
        hardware_monitor = (
            LibreHardwareMonitorClient(
                config.hardware_monitor_url,
                config.hardware_monitor_timeout_seconds,
            )
            if config.hardware_monitor_enabled
            else None
        )
        live_source = HostStateSource(
            WindowsSystemCollector(hardware_monitor),
            config.system_interval_seconds,
        )
        await live_source.initialize()
        collector_task = asyncio.create_task(
            live_source.run(),
            name="windows-system-collector",
        )
        source = live_source
    else:
        LOGGER.warning("Windows system collector is disabled; using synthetic telemetry")
        source = SyntheticStateSource()

    try:
        await WebSocketHost(config, auth_token, state_source=source).run()
    finally:
        if collector_task is not None:
            collector_task.cancel()
            await asyncio.gather(collector_task, return_exceptions=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop Companion Display host")
    parser.add_argument("--config", type=Path, default=Path("config/host.toml"))
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="validate configuration without starting the WebSocket server",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.error("%s", exc)
        return 2

    logging.basicConfig(level=config.log_level)
    if args.validate_config:
        LOGGER.info("Host configuration is valid")
        return 0

    auth_token = os.environ.get(config.auth_token_env)
    if auth_token is None:
        LOGGER.error("Required environment variable %s is not set", config.auth_token_env)
        return 2
    try:
        asyncio.run(run_application(config, auth_token))
    except KeyboardInterrupt:
        LOGGER.info("Host stopped")
    except (OSError, ValueError) as exc:
        LOGGER.error("Cannot start host: %s", exc)
        return 3
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
