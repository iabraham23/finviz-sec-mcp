"""Public Stocktwits REST client (no API key required for read endpoints)."""

from __future__ import annotations

import html
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE = "https://api.stocktwits.com/api/2"
TIMEOUT = 15
HEADERS = {
    # Stocktwits blocks generic python-requests; a stable UA is required.
    "User-Agent": "Mozilla/5.0 (compatible; finviz-sec-mcp/1.0)",
    "Accept": "application/json",
}


class StocktwitsClient:
    """Thin wrapper for trending symbols and per-symbol message streams."""

    @staticmethod
    def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{BASE}{path}"
        resp = requests.get(url, params=params or {}, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def trending_equities(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 30))
        data = self._get("/trending/symbols/equities.json", {"limit": limit})
        return data.get("symbols") or []

    def symbol_stream(self, ticker: str, limit: int = 30) -> list[dict[str, Any]]:
        ticker = ticker.upper().strip().lstrip("$")
        limit = max(1, min(limit, 30))
        data = self._get(f"/streams/symbol/{ticker}.json", {"limit": limit})
        return data.get("messages") or []

    @staticmethod
    def message_sentiment(message: dict[str, Any]) -> str | None:
        """Return Bullish, Bearish, or None from a stream message."""
        entities = message.get("entities") or {}
        sentiment = entities.get("sentiment") or {}
        basic = sentiment.get("basic")
        if basic in ("Bullish", "Bearish"):
            return basic
        return None

    @staticmethod
    def message_text(message: dict[str, Any]) -> str:
        body = message.get("body") or ""
        return html.unescape(body).replace("\n", " ").strip()
