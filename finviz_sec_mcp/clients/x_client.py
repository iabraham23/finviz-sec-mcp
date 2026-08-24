"""X (Twitter) API v2 read-only client — recent search."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE = "https://api.twitter.com/2"
TIMEOUT = 20


class XClient:
    """App-only Bearer token; read-only recent search."""

    def __init__(self) -> None:
        self._token = os.getenv("X_BEARER_TOKEN", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def search_recent(
        self,
        query: str,
        max_results: int = 15,
    ) -> list[dict[str, Any]]:
        """Run X API v2 recent search (last ~7 days)."""
        if not self.configured:
            raise RuntimeError("X_BEARER_TOKEN not set in finviz-sec-mcp/.env")

        max_results = max(10, min(max_results, 100))
        params = {
            "query": query,
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,lang",
        }
        resp = requests.get(
            f"{BASE}/tweets/search/recent",
            headers=self._headers(),
            params=params,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") or []

    @staticmethod
    def format_tweet(tweet: dict[str, Any]) -> str:
        created = (tweet.get("created_at") or "")[:19]
        text = (tweet.get("text") or "").replace("\n", " ")
        metrics = tweet.get("public_metrics") or {}
        likes = metrics.get("like_count", 0)
        rts = metrics.get("retweet_count", 0)
        if len(text) > 220:
            text = text[:217] + "..."
        return f"{created}  ♥{likes} ↻{rts}  {text}"
