"""Raspberry Pi composition root."""

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from pi.config import ConfigError, PiConfig, load_config
from pi.display import DisplayBackend, DisplayError, FramebufferBackend, HeadlessBackend
from pi.network import PiNetworkClient
from pi.renderer import FixedRateRenderer, color_bars_rgb565
from pi.state import LatestStateStore

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop Companion Display renderer")
    parser.add_argument("--config", type=Path, default=Path("config/pi.toml"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--display-test",
        action="store_true",
        help="write RGB565 color bars to the configured display and exit",
    )
    modes.add_argument(
        "--network-test",
        action="store_true",
        help="connect to the host and log received synthetic state",
    )
    modes.add_argument(
        "--run-display",
        action="store_true",
        help="connect to the host and render the live dashboard",
    )
    return parser


def build_display(config_backend: str, device: Path, width: int, height: int) -> DisplayBackend:
    """Construct a display backend without opening hardware."""

    backend = config_backend
    if backend == "auto":
        backend = "framebuffer" if device.exists() else "headless"
    if backend == "framebuffer":
        return FramebufferBackend(device, width, height)
    if backend == "headless":
        return HeadlessBackend(width, height)
    raise DisplayError(f"display backend {backend!r} is not implemented")


async def monitor_network(store: LatestStateStore) -> None:
    while True:
        await asyncio.sleep(2.0)
        snapshot = store.snapshot()
        fft = store.consume_fft()
        cpu = (
            snapshot.state.system.cpu_usage_percent
            if snapshot.state is not None and snapshot.state.system is not None
            else None
        )
        LOGGER.info(
            "Network test connected=%s sequence=%d cpu=%s fft_bins=%d overwritten_fft=%d",
            snapshot.connected,
            snapshot.last_sequence,
            f"{cpu:.1f}%" if cpu is not None else "n/a",
            len(fft.bins) if fft is not None else 0,
            snapshot.dropped_fft_frames,
        )


async def run_network_test(config: PiConfig, auth_token: str) -> None:
    store = LatestStateStore()
    client = PiNetworkClient(config, auth_token, store)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(client.run())
        tasks.create_task(monitor_network(store))


async def run_display_application(config: PiConfig, auth_token: str) -> None:
    store = LatestStateStore()
    client = PiNetworkClient(config, auth_token, store)
    display = build_display(
        config.display_backend,
        config.framebuffer_device,
        config.width,
        config.height,
    )
    renderer = FixedRateRenderer(display, store, config.target_fps)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(client.run())
        tasks.create_task(renderer.run())


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.error("%s", exc)
        return 2

    logging.basicConfig(level=config.log_level)
    if args.network_test or args.run_display:
        auth_token = os.environ.get(config.auth_token_env)
        if auth_token is None:
            LOGGER.error("Required environment variable %s is not set", config.auth_token_env)
            return 2
        try:
            operation = (
                run_display_application(config, auth_token)
                if args.run_display
                else run_network_test(config, auth_token)
            )
            asyncio.run(operation)
        except KeyboardInterrupt:
            LOGGER.info("Pi application stopped")
        except (DisplayError, ExceptionGroup, ValueError) as exc:
            LOGGER.error("Cannot start Pi application: %s", exc)
            return 3
        return 0

    if not args.display_test:
        LOGGER.warning(
            "Pi configuration is valid; use --display-test, --network-test, or --run-display"
        )
        return 0

    display = build_display(
        config.display_backend,
        config.framebuffer_device,
        config.width,
        config.height,
    )
    try:
        display.open()
        display.write_frame(color_bars_rgb565(config.width, config.height))
    except DisplayError as exc:
        LOGGER.error("%s", exc)
        return 3
    finally:
        display.close()

    LOGGER.info(
        "Wrote RGB565 test pattern to %s (%dx%d, rotation metadata %d degrees)",
        config.framebuffer_device,
        config.width,
        config.height,
        config.orientation,
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
