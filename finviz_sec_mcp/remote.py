"""
Remote streamable HTTP entrypoint for the MCP server.
"""

from __future__ import annotations

from .app_factory import build_server


def main() -> None:
    server = build_server("remote")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
