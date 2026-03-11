"""
Server factory for local stdio and remote streamable HTTP modes.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .tools.analyst import register_analyst_tools
from .tools.fundamentals import register_fundamentals_tools
from .tools.screener import register_screener_tools
from .tools.sec_filings import register_sec_tools
from .tools.sector_analysis import register_sector_tools

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure process-wide logging once."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))


def register_all_tools(server: FastMCP) -> FastMCP:
    """Register every MCP tool on the provided server."""
    register_screener_tools(server)
    register_fundamentals_tools(server)
    register_sec_tools(server)
    register_sector_tools(server)
    register_analyst_tools(server)
    return server

def build_server(mode: Literal["local", "remote"] = "local") -> FastMCP:
    """Build the MCP server for the requested runtime mode."""
    configure_logging()

    common_kwargs = {
        "name": "Finviz + SEC EDGAR Stock Research",
        "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
    }

    if mode == "remote":
        from .http_routes import register_http_routes

        server = FastMCP(
            **common_kwargs,
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", os.getenv("MCP_PORT", "8000"))),
            streamable_http_path=os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp"),
        )
        register_all_tools(server)
        register_http_routes(server)
        logger.info("Finviz + SEC EDGAR remote MCP configured")
        return server

    server = FastMCP(**common_kwargs)
    register_all_tools(server)
    logger.info("Finviz + SEC EDGAR local MCP configured")
    return server
