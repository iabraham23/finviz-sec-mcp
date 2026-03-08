#!/usr/bin/env python3
"""
Finviz + SEC EDGAR MCP Server
A free MCP server for stock research using Finviz screening and SEC EDGAR filings.
No paid subscriptions required.
"""

import logging
import os
from mcp.server.fastmcp import FastMCP

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

server = FastMCP("Finviz + SEC EDGAR Stock Research")

# ── Register tool modules ──────────────────────────────────────────────
from .tools.screener import register_screener_tools
from .tools.fundamentals import register_fundamentals_tools
from .tools.sec_filings import register_sec_tools
from .tools.sector_analysis import register_sector_tools
from .tools.analyst import register_analyst_tools

register_screener_tools(server)
register_fundamentals_tools(server)
register_sec_tools(server)
register_sector_tools(server)
register_analyst_tools(server)

logger.info("Finviz + SEC EDGAR MCP Server initialized with all tools")


def main():
    """Entry point for the MCP server."""
    server.run()


if __name__ == "__main__":
    main()
