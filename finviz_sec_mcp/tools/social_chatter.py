"""
Social chatter tools: Stocktwits (live), optional Grok (xAI), Asia headline screen.

X (Twitter) and Truth Social require separate API keys — see ops/SOCIAL_FEEDS.md.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import requests
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient
from ..clients.stocktwits_client import StocktwitsClient
from ..clients.x_client import XClient

logger = logging.getLogger(__name__)

finviz = FinvizClient()
stocktwits = StocktwitsClient()
x_client = XClient()

WATCHLIST_DIR = Path(__file__).resolve().parents[2] / "watchlists"

# Headlines / headwinds tied to Asia session → US ADR open
ASIA_HEADWIND_KEYWORDS = (
    "china",
    "chinese",
    "hong kong",
    "hk",
    "taiwan",
    "japan",
    "asia",
    "yuan",
    "rmb",
    "tariff",
    "sanction",
    "regulator",
    "dilut",
    "placing",
    "offering",
    "burry",
    "weak",
    "selloff",
    "sell-off",
    "risk-off",
    "fade",
    "downgrade",
    "probe",
    "investigation",
    "delist",
)

ASIA_TAILWIND_KEYWORDS = (
    "beat",
    "raise",
    "guidance up",
    "upgrade",
    "stimulus",
    "easing",
    "rebound",
    "strong",
    "buyback",
    "approval",
)


def _load_tickers(filename: str) -> set[str]:
    path = WATCHLIST_DIR / filename
    if not path.exists():
        return set()
    tickers: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.add(line.upper())
    return tickers


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [k for k in keywords if k in lower]


def _score_text(text: str) -> tuple[int, int, list[str], list[str]]:
    headwinds = _keyword_hits(text, ASIA_HEADWIND_KEYWORDS)
    tailwinds = _keyword_hits(text, ASIA_TAILWIND_KEYWORDS)
    return len(headwinds), len(tailwinds), headwinds, tailwinds


def _run_x_search(query: str, max_results: int) -> List[TextContent]:
    if not x_client.configured:
        return [
            TextContent(
                type="text",
                text="X_BEARER_TOKEN not set in finviz-sec-mcp/.env — restart MCP after adding.",
            )
        ]
    tweets = x_client.search_recent(query, max_results=max_results)
    lines = [
        "X recent search",
        f"Query: {query}",
        "=" * 60,
        "",
    ]
    if not tweets:
        lines.append("No posts matched.")
        return [TextContent(type="text", text="\n".join(lines))]

    for tw in tweets:
        lines.append(f"  {XClient.format_tweet(tw)}")
    lines.append(f"\n{len(tweets)} posts")
    return [TextContent(type="text", text="\n".join(lines))]


def register_social_chatter_tools(server):
    """Register Stocktwits + Asia chatter screening tools."""

    @server.tool()
    def get_stocktwits_trending(
        limit: int = 20,
        theme_only: bool = True,
    ) -> List[TextContent]:
        """Trending US equities on Stocktwits by message volume.

        Args:
            limit: Max symbols (1–30).
            theme_only: If true, keep only tickers in watchlists/nick_themes.txt.
        """
        try:
            symbols = stocktwits.trending_equities(limit=limit)
            themes = _load_tickers("nick_themes.txt") if theme_only else set()

            lines = [
                "Stocktwits Trending Equities",
                "=" * 60,
                "",
            ]
            shown = 0
            for sym in symbols:
                ticker = (sym.get("symbol") or "").upper()
                if theme_only and ticker not in themes:
                    continue
                rank = (sym.get("trends") or {}).get("all", "?")
                score = sym.get("trending_score", "?")
                watches = sym.get("watchlist_count", "?")
                title = sym.get("title", "")
                sector = sym.get("sector", "")
                lines.append(
                    f"  #{rank} {ticker}  score={score}  watches={watches}  "
                    f"{sector} — {title}"
                )
                shown += 1

            if theme_only and shown == 0:
                lines.append(
                    "  (No trending symbols intersect nick_themes.txt right now.)"
                )
                lines.append(
                    "  Re-run with theme_only=false to see full market trending list."
                )
            elif not theme_only:
                lines.append(f"\nTotal: {len(symbols)} symbols")

            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            logger.error("get_stocktwits_trending: %s", e)
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_stocktwits_stream(
        ticker: str,
        limit: int = 15,
    ) -> List[TextContent]:
        """Recent Stocktwits messages for one ticker (sentiment tags when present).

        Args:
            ticker: Symbol, e.g. BABA.
            limit: Messages to return (max 30).
        """
        try:
            messages = stocktwits.symbol_stream(ticker, limit=limit)
            lines = [
                f"Stocktwits stream — {ticker.upper()}",
                "=" * 60,
                "",
            ]
            if not messages:
                lines.append("No recent messages.")
                return [TextContent(type="text", text="\n".join(lines))]

            for msg in messages:
                created = (msg.get("created_at") or "")[:19]
                sent = stocktwits.message_sentiment(msg) or "—"
                body = stocktwits.message_text(msg)
                if len(body) > 200:
                    body = body[:197] + "..."
                hw, tw, _, _ = _score_text(body)
                flag = ""
                if hw:
                    flag = " [headwind keywords]"
                elif tw:
                    flag = " [tailwind keywords]"
                lines.append(f"  {created}  [{sent}]{flag}  {body}")

            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            logger.error("get_stocktwits_stream: %s", e)
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def screen_asia_social_chatter(
        max_tickers: int = 12,
    ) -> List[TextContent]:
        """Morning screen: Asia ADRs + theme overlap, Stocktwits chatter, Finviz headlines.

        Ranks tickers by bearish message ratio and headwind keyword hits.
        Use before US open when Asia/ADR headlines may drive gaps (BABA, PDD, TSM, etc.).

        Args:
            max_tickers: How many ADR/theme symbols to scan (default 12).
        """
        try:
            asia = _load_tickers("asia_adr.txt")
            themes = _load_tickers("nick_themes.txt")
            # Scan Asia ADR book; highlight names also in theme universe
            universe = sorted(asia if asia else {"BABA", "BIDU", "TSM", "PDD", "XPEV"})

            trending = {
                (s.get("symbol") or "").upper()
                for s in stocktwits.trending_equities(limit=30)
            }

            lines = [
                "Asia / ADR Social Chatter Screen",
                "=" * 60,
                "",
                f"Universe ({len(universe)}): {', '.join(universe[:max_tickers])}",
                f"In nick_themes.txt: {', '.join(t for t in universe if t in themes) or 'none'}",
                f"Stocktwits trending hits in universe: "
                f"{', '.join(t for t in universe if t in trending) or 'none'}",
                "",
            ]

            rows: list[dict] = []
            for ticker in universe[:max_tickers]:
                messages = stocktwits.symbol_stream(ticker, limit=20)
                bullish = bearish = neutral = 0
                headwind_score = 0
                sample_bear: list[str] = []
                sample_hw: list[str] = []

                for msg in messages:
                    text = stocktwits.message_text(msg)
                    sent = stocktwits.message_sentiment(msg)
                    hw, tw, hw_kw, _ = _score_text(text)
                    headwind_score += hw * 2 + (1 if sent == "Bearish" else 0)
                    headwind_score -= tw

                    if sent == "Bullish":
                        bullish += 1
                    elif sent == "Bearish":
                        bearish += 1
                        if len(sample_bear) < 2:
                            sample_bear.append(text[:120])
                    else:
                        neutral += 1
                    if hw_kw and len(sample_hw) < 2:
                        sample_hw.append(f"{ticker}: {', '.join(hw_kw)} — {text[:80]}")

                news_snip = ""
                try:
                    news = finviz.get_news(ticker)
                    if news and len(news[0]) >= 2:
                        news_snip = str(news[0][1])[:100]
                except Exception:
                    news_snip = ""

                total_tagged = bullish + bearish
                bear_ratio = bearish / total_tagged if total_tagged else 0.0

                rows.append(
                    {
                        "ticker": ticker,
                        "trending": ticker in trending,
                        "bullish": bullish,
                        "bearish": bearish,
                        "neutral": neutral,
                        "bear_ratio": bear_ratio,
                        "headwind_score": headwind_score,
                        "news": news_snip,
                        "sample_bear": sample_bear,
                        "sample_hw": sample_hw,
                    }
                )

            rows.sort(
                key=lambda r: (r["headwind_score"], r["bear_ratio"]),
                reverse=True,
            )

            lines.append(
                f"{'Ticker':<6} {'Trnd':<5} {'Bull':<5} {'Bear':<5} "
                f"{'Bear%':<6} {'HW':<4}  Latest Finviz headline"
            )
            lines.append("-" * 72)
            for r in rows:
                lines.append(
                    f"{r['ticker']:<6} "
                    f"{'Y' if r['trending'] else 'n':<5} "
                    f"{r['bullish']:<5} {r['bearish']:<5} "
                    f"{r['bear_ratio']*100:5.0f}% {r['headwind_score']:<4}  "
                    f"{r['news'] or '—'}"
                )

            flagged = [r for r in rows if r["headwind_score"] >= 2 or r["bear_ratio"] >= 0.5]
            if flagged:
                lines.extend(["", "⚠ Headwind watch (chatter + keywords):", ""])
                for r in flagged[:5]:
                    lines.append(f"  {r['ticker']}:")
                    for s in r["sample_bear"]:
                        lines.append(f"    bearish: {s}")
                    for s in r["sample_hw"]:
                        lines.append(f"    keyword: {s}")
            else:
                lines.extend(["", "No strong headwind cluster in chatter (still verify PM gaps)."])

            sources = "Stocktwits + Finviz news"
            if x_client.configured:
                sources += " + X search"
            else:
                sources += " (add X_BEARER_TOKEN for X search)"
            lines.extend(["", f"Sources: {sources}."])
            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            logger.error("screen_asia_social_chatter: %s", e)
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def query_grok_market_chatter(
        prompt: str = (
            "Summarize overnight Asia market headwinds and ADR-relevant headlines "
            "for US traders (China/HK/Taiwan). List tickers and bull/bear bias. "
            "Be concise, bullet format."
        ),
    ) -> List[TextContent]:
        """Optional: ask xAI Grok for Asia/ADR headline summary (requires XAI_API_KEY in .env).

        Does not replace Stocktwits/Finviz — use for macro narrative cross-check only.
        """
        api_key = os.getenv("XAI_API_KEY", "").strip()
        if not api_key:
            return [
                TextContent(
                    type="text",
                    text=(
                        "XAI_API_KEY not set in finviz-sec-mcp/.env\n\n"
                        "Add key from https://console.x.ai/ then restart MCP.\n"
                        "Until then use screen_asia_social_chatter (Stocktwits + Finviz)."
                    ),
                )
            ]
        try:
            resp = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("XAI_MODEL", "grok-3-latest"),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a trading desk assistant. "
                                "Focus on verifiable market themes; flag uncertainty."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return [
                TextContent(
                    type="text",
                    text=f"Grok Asia/ADR brief\n{'='*40}\n\n{content}",
                )
            ]
        except Exception as e:
            logger.error("query_grok_market_chatter: %s", e)
            return [TextContent(type="text", text=f"Grok error: {e}")]

    @server.tool()
    def search_x_posts(
        query: str,
        max_results: int = 15,
    ) -> List[TextContent]:
        """Search recent X posts (last ~7 days). Read-only; requires X_BEARER_TOKEN in .env.

        Example query: ($BABA OR $PDD) (earnings OR china) -is:retweet lang:en

        Args:
            query: X search query (same syntax as X advanced search).
            max_results: 10–100 (default 15).
        """
        if not x_client.configured:
            return [
                TextContent(
                    type="text",
                    text="X_BEARER_TOKEN not set in finviz-sec-mcp/.env — restart MCP after adding.",
                )
            ]
        try:
            return _run_x_search(query, max_results)
        except Exception as e:
            logger.error("search_x_posts: %s", e)
            return [TextContent(type="text", text=f"X search error: {e}")]

    @server.tool()
    def search_x_asia_headlines(max_results: int = 15) -> List[TextContent]:
        """Preset X search for Asia ADR / China macro headlines (Mon premarket use).

        Requires X_BEARER_TOKEN in .env. Read-only, low volume.
        """
        query = (
            "($BABA OR $PDD OR $TSM OR $XPEV OR $BIDU) "
            "(china OR hong kong OR earnings OR ADR OR gap OR placing) "
            "-is:retweet lang:en"
        )
        try:
            return _run_x_search(query, max_results)
        except Exception as e:
            logger.error("search_x_asia_headlines: %s", e)
            return [TextContent(type="text", text=f"X search error: {e}")]
