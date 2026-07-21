"""Windows host composition root."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from pc.config import ConfigError, load_config

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop Companion Display host")
    parser.add_argument("--config", type=Path, default=Path("config/host.toml"))
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
    LOGGER.warning(
        "Host configuration is valid; runtime networking and collectors are not implemented"
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
