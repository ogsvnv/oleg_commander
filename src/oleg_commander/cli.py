"""Command-line interface for the Oleg Commander MCP service."""

import argparse
import asyncio
import sys

from .config import Config
from .server import OlegCommanderServer


def main() -> None:
    """Run the MCP server or a local diagnostic."""
    parser = argparse.ArgumentParser(prog="oleg-commander")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Run the MCP server")
    start.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http"),
        help="Override the configured MCP transport",
    )
    subparsers.add_parser("doctor", help="Show installed runtime settings")
    subparsers.add_parser("status", help="Show implementation status")

    args = parser.parse_args()
    if args.command == "start":
        config = Config()
        if args.transport:
            config.server.transport = args.transport
        try:
            asyncio.run(OlegCommanderServer(config).start())
        except KeyboardInterrupt:
            pass
    elif args.command == "doctor":
        config = Config()
        print(f"Python: {sys.version.split()[0]}")
        print(f"MCP transport: {config.server.transport}")
        print(f"Read-only: {config.security.read_only}")
        print(f"Approval required: {config.security.require_approval}")
    else:
        print("Implemented: local MCP server, filesystem, Git, limited terminal")
        print("Not implemented: SSH execution, Docker, systemd, process control")


if __name__ == "__main__":
    main()
