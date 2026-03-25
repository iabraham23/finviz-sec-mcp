"""
Analyst Ratings, Insider Activity, and News Tools
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()
EARNINGS_NEWS_KEYWORDS = (
    "earnings",
    "results",
    "guidance",
    "conference call",
    "transcript",
    "webcast",
)


def register_analyst_tools(server):
    """Register analyst, insider, and news tools."""

    @server.tool()
    def get_analyst_ratings(
        ticker: str, count: int = 10
    ) -> List[TextContent]:
        """Get analyst price targets and ratings for a stock from Finviz.
        Shows date, analyst firm, rating action, and price target (from/to).
        Useful for gauging sell-side sentiment and consensus target price.

        Args:
            ticker: Stock ticker symbol.
            count: Number of recent ratings to return (default 10).
        """
        try:
            targets = client.get_analyst_targets(ticker, last_ratings=count)
            if not targets:
                return [TextContent(
                    type="text",
                    text=f"No analyst ratings found for {ticker.upper()}",
                )]

            lines = [
                f"Analyst Ratings for {ticker.upper()}",
                "=" * 75,
                "",
                f"{'Date':<12}{'Action':<14}{'Analyst':<20}{'Rating':<16}{'Target':>13}",
                "-" * 75,
            ]

            for t in targets:
                date = t.get("date", "?")
                category = t.get("category", "")[:12]
                analyst = t.get("analyst", "?")[:18]
                rating = t.get("rating", "?")[:14]
                target_from = t.get("target_from", "")
                target_to = t.get("target_to", "")
                target_single = t.get("target", "")
                if target_from and target_to:
                    target_str = f"${target_from}→${target_to}"
                elif target_to:
                    target_str = f"${target_to}"
                elif target_single:
                    target_str = f"${target_single}"
                else:
                    target_str = "-"

                lines.append(
                    f"{date:<12}{category:<14}{analyst:<20}{rating:<16}{target_str:>13}"
                )

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_insider_activity(ticker: str) -> List[TextContent]:
        """Get recent insider trading activity (buys/sells) from Finviz.
        Shows insider name, relationship to company, transaction type, date,
        share count, and dollar value. Useful for gauging management conviction.
        For SEC Form 3/4/5 filings with EDGAR links, use get_insider_filings.

        Args:
            ticker: Stock ticker symbol.
        """
        try:
            insiders = client.get_insider(ticker)
            if not insiders:
                return [TextContent(
                    type="text",
                    text=f"No insider activity found for {ticker.upper()}",
                )]

            lines = [
                f"Insider Activity for {ticker.upper()}",
                "=" * 65,
                "",
            ]

            for trade in insiders[:15]:
                name = trade.get("Insider Trading", "?")
                relationship = trade.get("Relationship", "?")
                transaction = trade.get("Transaction", "?")
                date = trade.get("Date", "?")
                shares = trade.get("#Shares", "?")
                value = trade.get("Value ($)", "?")

                lines.append(f"▸ {name} ({relationship})")
                lines.append(
                    f"  {transaction} — {date} | "
                    f"Shares: {shares} | Value: ${value}"
                )
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_stock_news(ticker: str, count: int = 10) -> List[TextContent]:
        """Get recent news headlines for a stock from Finviz.
        Returns headlines with source, timestamp, and URL.
        For earnings-specific headlines only, use get_earnings_news.

        Args:
            ticker: Stock ticker symbol.
            count: Number of headlines to return (default 10).
        """
        try:
            news = client.get_news(ticker)
            if not news:
                return [TextContent(
                    type="text",
                    text=f"No news found for {ticker.upper()}",
                )]

            lines = [
                f"Recent News for {ticker.upper()}",
                "=" * 60,
                "",
            ]

            for item in news[:count]:
                # News returns tuples: (timestamp, headline, url, source)
                if len(item) >= 4:
                    timestamp, headline, url, source = item[0], item[1], item[2], item[3]
                    lines.append(f"▸ [{source}] {headline}")
                    lines.append(f"  {timestamp} — {url}")
                    lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_earnings_news(ticker: str, count: int = 10) -> List[TextContent]:
        """Get earnings-related headlines for a stock from Finviz.
        Filters the full news feed to only headlines containing keywords:
        earnings, results, guidance, conference call, webcast, transcript.
        Use this for post-earnings analysis or when building an earnings update.
        For all news (not just earnings), use get_stock_news.

        Args:
            ticker: Stock ticker symbol.
            count: Number of matching headlines to return (default 10).
        """
        try:
            news = client.get_news(ticker)
            if not news:
                return [TextContent(
                    type="text",
                    text=f"No news found for {ticker.upper()}",
                )]

            filtered = []
            for item in news:
                if len(item) < 4:
                    continue
                headline = item[1]
                if any(keyword in headline.lower() for keyword in EARNINGS_NEWS_KEYWORDS):
                    filtered.append(item)

            if not filtered:
                return [TextContent(
                    type="text",
                    text=(
                        f"No earnings-related headlines found for {ticker.upper()} "
                        "in the current Finviz news feed."
                    ),
                )]

            lines = [
                f"Earnings News for {ticker.upper()}",
                "=" * 60,
                "",
            ]

            for item in filtered[:count]:
                timestamp, headline, url, source = item[0], item[1], item[2], item[3]
                lines.append(f"▸ [{source}] {headline}")
                lines.append(f"  {timestamp} — {url}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]
