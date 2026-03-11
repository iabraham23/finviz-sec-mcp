#!/usr/bin/env python3
"""Local stdio entrypoint for the MCP server."""

from .app_factory import build_server

server = build_server("local")


def main():
    """Entry point for local stdio usage."""
    server.run()


if __name__ == "__main__":
    main()
