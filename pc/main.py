"""Windows host composition root."""

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from pc.audio import WasapiLoopbackFftCollector
from pc.collectors import (
    LibreHardwareMonitorClient,
    WindowsMediaSessionCollector,
    WindowsSystemCollector,
)
from pc.config import ConfigError, HostConfig, load_config
from pc.network import StateSource, WebSocketHost
from pc.state import HostStateSource, SyntheticStateSource

LOGGER = logging.getLogger(__name__)


async def run_application(config: HostConfig, auth_token: str) -> None:
    source: StateSource
    collector_task: asyncio.Task[None] | None = None
    system_collector = None
    media_collector = None
    fft_collector = None

    if config.system_collector_enabled:
        hardware_monitor = (
            LibreHardwareMonitorClient(
                config.hardware_monitor_url,
                config.hardware_monitor_timeout_seconds,
            )
            if config.hardware_monitor_enabled
            else None
        )
        system_collector = WindowsSystemCollector(hardware_monitor)
    else:
        LOGGER.warning("Windows system collector is disabled; using synthetic telemetry")

    if config.media_collector_enabled:
        try:
            media_collector = WindowsMediaSessionCollector()
        except RuntimeError as exc:
            LOGGER.warning("%s; using synthetic media metadata", exc)
    else:
        LOGGER.warning("Windows media collector is disabled; using synthetic media metadata")

    if config.fft_collector_enabled:
        try:
            fft_collector = WasapiLoopbackFftCollector(fft_size=config.fft_size)
        except RuntimeError as exc:
            LOGGER.warning("%s; using synthetic FFT frames", exc)
    else:
        LOGGER.warning("WASAPI loopback FFT is disabled; using synthetic FFT frames")

    if system_collector is None and media_collector is None and fft_collector is None:
        source = SyntheticStateSource()
    else:
        live_source = HostStateSource(
            system_collector=system_collector,
            system_interval_seconds=config.system_interval_seconds,
            media_collector=media_collector,
            media_interval_seconds=config.media_interval_seconds,
            fft_collector=fft_collector,
            album_art_enabled=config.album_art_enabled,
        )
        await live_source.initialize()
        collector_task = asyncio.create_task(live_source.run(), name="host-collectors")
        source = live_source

    try:
        await WebSocketHost(config, auth_token, state_source=source).run()
    finally:
        if collector_task is not None:
            collector_task.cancel()
            await asyncio.gather(collector_task, return_exceptions=True)
        elif fft_collector is not None:
            fft_collector.stop()


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
