"""Windows host composition root."""

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from pc.config import ConfigError, load_config
from pc.network import WebSocketHost

LOGGER = logging.getLogger(__name__)


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
        host = WebSocketHost(config, auth_token)
        asyncio.run(host.run())
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
