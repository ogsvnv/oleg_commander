"""Command-line interface for the Oleg Commander MCP service."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from .services.approval_service import ApprovalService
from .audit import AuditLogger

from .config import Config
from .server import OlegCommanderServer


def main() -> None:
    """Run the MCP server or a local diagnostic."""
    parser = argparse.ArgumentParser(prog="oleg-commander")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Run the MCP server")
    start.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http", "https"),
        help="Override the configured MCP transport",
    )
    subparsers.add_parser("doctor", help="Show installed runtime settings")
    subparsers.add_parser("status", help="Show implementation status")
    subparsers.add_parser("approvals", help="List pending approvals")
    for verb in ("approve", "reject"):
        choice = subparsers.add_parser(verb, help=f"{verb.title()} one local approval")
        choice.add_argument("id", help="Request ID shown by the MCP tool")
    logs = subparsers.add_parser("logs", help="Show redacted local audit events")
    logs.add_argument("--limit", type=int, default=20)


    args = parser.parse_args()
    if args.command == "start":
        config = Config.load()
        if args.transport:
            config.server.transport = args.transport
        try:
            asyncio.run(OlegCommanderServer(config).start())
        except KeyboardInterrupt:
            pass
    elif args.command == "doctor":
        config = Config.load()
        print(f"Python: {sys.version.split()[0]}")
        print(f"MCP transport: {config.server.transport}")
        print(f"Read-only: {config.security.read_only}")
        print(f"Approval required: {config.security.require_approval}")
    elif args.command == "approvals":
        for entry in ApprovalService().list_requests():
            expiry = datetime.fromtimestamp(entry["expires"], timezone.utc).isoformat()
            print(
                f'{entry["id"]}  {entry["status"]}  {entry["tool"]}  '
                f'{entry["target"]}  sha256:{entry["digest"][:16]}  expires:{expiry}'
            )
    elif args.command in ("approve", "reject"):
        config = Config.load()
        if not config.logging.audit_enabled:
            parser.error("Audit must be enabled to decide approvals")
        audit = AuditLogger()
        # Audit the decision before allowing a new execution.
        audit.record(tool="approval."+args.command, status="requested", request_id=args.id)
        if ApprovalService().decide(args.id, approve=args.command == "approve"):
            audit.record(tool="approval."+args.command, status="success", request_id=args.id)
            print("Decision saved. Retry the same MCP invocation.")
        else:
            print("Approval not found, expired or already decided", file=sys.stderr)
            sys.exit(1)
    elif args.command == "logs":
        for entry in AuditLogger().recent(args.limit):
            print(
                f'{entry["timestamp"]} {entry["tool"]} {entry["status"]} '
                f'{entry["error_code"] or ""} {entry["request_id"] or ""}'
            )
    else:
        print("Implemented: MCP, SSH, filesystem, Git and allowlisted diagnostics")
        print("Process termination, OAuth and advanced approval UI pending")


if __name__ == "__main__":
    main()
