"""
Custom HTTP routes for the remote deployment.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def register_http_routes(server) -> None:
    """Register extra HTTP routes for the remote deployment."""

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(request: Request) -> Response:
        return JSONResponse({"status": "ok"})
