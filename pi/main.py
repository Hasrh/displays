"""Raspberry Pi composition root."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from pi.config import ConfigError, load_config
from pi.display import DisplayBackend, DisplayError, FramebufferBackend, HeadlessBackend
from pi.renderer import color_bars_rgb565

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop Companion Display renderer")
    parser.add_argument("--config", type=Path, default=Path("config/pi.toml"))
    parser.add_argument(
        "--display-test",
        action="store_true",
        help="write RGB565 color bars to the configured display and exit",
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


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.error("%s", exc)
        return 2

    logging.basicConfig(level=config.log_level)
    if not args.display_test:
        LOGGER.warning(
            "Pi configuration is valid; use --display-test to verify the framebuffer. "
            "Networking and pages are not implemented"
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
