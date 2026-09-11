from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigurationError, Settings
from .imap_client import BridgeError, ProtonBridgeClient


def _doctor() -> int:
    try:
        settings = Settings.from_env()
        result = ProtonBridgeClient(settings).doctor()
        result["config"] = settings.public_summary()
        print(json.dumps(result, indent=2))
        return 0
    except (ConfigurationError, BridgeError) as exc:
        print(f"doctor failed: {exc}", file=sys.stderr)
        return 2


def _serve(host: str | None, port: int | None) -> int:
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    bind_host = host or settings.bind_host
    bind_port = port or settings.bind_port
    if bind_host not in {"127.0.0.1", "::1", "localhost"}:
        print(
            "Refusing non-loopback bind. Use Secure MCP Tunnel from this machine instead.",
            file=sys.stderr,
        )
        return 2

    from .server import mcp

    print(f"Starting protonmail-mcp on http://{bind_host}:{bind_port}/mcp", file=sys.stderr)
    mcp.run(
        transport="streamable-http",
        host=bind_host,
        port=bind_port,
        stateless_http=True,
        json_response=True,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protonmail-mcp",
        description="Read-only MCP access to Proton Mail through Proton Mail Bridge",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="verify Bridge configuration without reading messages")

    serve = subparsers.add_parser("serve", help="start the local Streamable HTTP MCP server")
    serve.add_argument("--host", default=None, help="loopback bind host; default from environment")
    serve.add_argument("--port", type=int, default=None, help="bind port; default from environment")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return _doctor()
    if args.command == "serve":
        return _serve(args.host, args.port)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
