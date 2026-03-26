#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from app import App
from config import generate_example_config, load_config
from utils import NoEcho


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Config-file driven gerrit approvals dashboard ",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="approvals.json",
        help="Path to JSON config file (default: approvals.json)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Generate an example config file and exit",
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    if args.init:
        if config_path.exists():
            print(f"Config file already exists: {config_path}")
            sys.exit(1)
        generate_example_config(config_path)
        print(f"Example config written to {config_path} - edit it and run again.")
        sys.exit(0)

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Run with --init to generate an example, or create it manually.")
        sys.exit(1)

    console = Console()
    try:
        changes, interval, default_host = load_config(config_path)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        sys.exit(1)

    app = App(config_path, changes, interval, default_host)
    app.run()


if __name__ == "__main__":
    with NoEcho():
        main()
