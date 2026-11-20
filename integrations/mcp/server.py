"""NEXUS MCP Server Gateway Entrypoint & Re-Export (Stdio + Streamable HTTP)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.daemon import NexusDaemon
from core.nexus_core.mcp_server import (
    MCP_PROTOCOL_VERSION,
    MCPServerConfig,
    MCPStreamableHttpServer,
    NexusMCPServer,
)

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCPServerConfig",
    "MCPStreamableHttpServer",
    "NexusMCPServer",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS MCP Server (stdio)")
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="MCP local transport mode (default: stdio)",
    )
    parser.parse_args(argv)

    config = NexusDaemonConfig.from_env()
    daemon = NexusDaemon(config=config)

    async def _run() -> None:
        await daemon.start(start_network=False)
        try:
            await daemon.mcp.serve_stdio_lines()
        finally:
            await daemon.stop()

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
