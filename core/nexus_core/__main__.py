"""NEXUS CLI Entry Point for Standalone Daemon & Windows Sidecar Execution."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from core.nexus_core.config import APP_VERSION, NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS Core Background Daemon")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print NEXUS Core version and exit cleanly.",
    )
    parser.add_argument(
        "--health-once",
        action="store_true",
        help="Start subsystems, print JSON health report, and shut down gracefully.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start independent loopback HTTP, WebSocket, and MCP Streamable HTTP servers until interrupted.",
    )
    parser.add_argument(
        "--mcp-stdio",
        action="store_true",
        help="Run the NEXUS MCP server over local stdio transport.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override persistent NEXUS data directory (SQLite, tokens, checkpoints, logs).",
    )
    parser.add_argument(
        "--bind-host",
        type=str,
        default=None,
        help="Override loopback bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--rest-port",
        type=int,
        default=None,
        help="Override REST gateway port (default: 47100).",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Write rotating structured JSON logs to the specified file path.",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(json.dumps({"service": "nexus-python-daemon", "version": APP_VERSION}))
        return 0

    if args.data_dir:
        os.environ["NEXUS_DATA_DIR"] = str(Path(args.data_dir).expanduser())
        os.environ.setdefault(
            "NEXUS_SQLITE_PATH",
            str(Path(args.data_dir).expanduser() / "nexus.db"),
        )
    if args.bind_host:
        os.environ["NEXUS_BIND_HOST"] = args.bind_host
    if args.rest_port is not None:
        os.environ["NEXUS_REST_PORT"] = str(args.rest_port)

    config = NexusDaemonConfig.from_env()
    if args.log_file:
        config.log_file = Path(args.log_file).expanduser()
    elif config.log_file is None:
        config.log_file = config.data_dir / "logs" / "nexus-daemon.log"

    daemon = NexusDaemon(config=config)

    if args.health_once:
        async def run_once() -> None:
            await daemon.start(start_network=False)
            try:
                report = await daemon.health()
                print(json.dumps(report, indent=2))
            finally:
                await daemon.stop()

        asyncio.run(run_once())
        return 0

    if args.mcp_stdio:
        async def run_mcp_stdio() -> None:
            await daemon.start(start_network=False)
            try:
                await daemon.mcp.serve_stdio_lines()
            finally:
                await daemon.stop()

        asyncio.run(run_mcp_stdio())
        return 0

    if args.serve:
        asyncio.run(daemon.serve_forever())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
