#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from app import App
from config import (
    generate_example_changes,
    generate_example_toml,
    load_changes,
    load_toml_config,
)
from utils import NoEcho


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Config-file driven gerrit approvals dashboard",
    )

    parser.add_argument(
        "config",
        nargs="?",
        default="config.toml",
        help="Path to TOML config file (default: approvals.toml)",
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Generate example approvals.toml and approvals.json, then exit",
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Start MCP server for gerrit approvals",
    )

    args = parser.parse_args()
    config_path = Path(args.config)

    if args.init:
        changes_path = config_path.parent / "approvals.json"
        generate_example_toml(config_path)
        generate_example_changes(changes_path)
        print(f"Created {config_path} and {changes_path} — edit them and run again.")
        sys.exit(0)

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Run with --init to generate an example, or create it manually.")
        sys.exit(1)

    cfg = load_toml_config(config_path)
    changes = load_changes(cfg.changes_file, cfg.default_host, cfg.default_port)

    app = App(
        config_path, cfg.changes_file, changes, cfg.interval, cfg.default_host, cfg.default_port, cfg.email, cfg.editor
    )

    if args.mcp:
        from mcp_background import BackgroundMCPServer
        BackgroundMCPServer(app)

    app.run()


if __name__ == "__main__":
    with NoEcho():
        main()
