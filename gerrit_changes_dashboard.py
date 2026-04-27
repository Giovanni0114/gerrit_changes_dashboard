#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from app import App
from config import (
    AppConfig,
    generate_example_config,
)
from logs import app_logger, setup_logging
from utils import NoEcho


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gerrit Changes Dashboard",
    )

    parser.add_argument(
        "config",
        nargs="?",
        default="config.toml",
        help="Path to TOML config file (default: config.toml)",
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Generate example config.toml, then exit",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the SSH data cache file before starting",
    )

    args = parser.parse_args()
    config_path = Path(args.config)

    if args.init:
        generate_example_config(config_path)
        print(f"Created {config_path} - edit it and run again.")
        sys.exit(0)

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Run with --init to generate an example, or create it manually.")
        sys.exit(1)

    config = AppConfig(config_path)

    if args.clear_cache:
        config.cache_path.unlink(missing_ok=True)
        print(f"Cleared cache: {config.cache_path}")

    log_path = setup_logging(config.log_path)
    app_logger().info("startup config=%s logs=%s", config_path, log_path)

    app = App(config)
    app.run()


if __name__ == "__main__":
    with NoEcho():
        main()
