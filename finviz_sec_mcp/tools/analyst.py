"""
Analyst Ratings, Insider Activity, and News Tools
Priorities 5–7 in the value research workflow.
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()


def register_analyst_tools(server):
    """Register analyst, insider, and news tools."""

    @server.tool()
    def get_analyst_ratings(
        ticker: str, count: int = 10
    ) -> List[TextContent]:
        """Get analyst price targets and ratings for a stock.

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
                "=" * 60,
                "",
                f"{'Date':<12}{'Analyst':<22}{'Rating':<16}{'Target':>10}",
                "-" * 60,
            ]

            for t in targets:
                date = t.get("date", "?")
                analyst = t.get("analyst", "?")[:20]
                rating = t.get("rating", "?")[:14]
                target_from = t.get("target_from", "")
                target_to = t.get("target_to", "")
                if target_from and target_to:
                    target_str = f"${target_from}→${target_to}"
                elif target_to:
                    target_str = f"${target_to}"
                else:
                    target_str = "-"

                lines.append(
                    f"{date:<12}{analyst:<22}{rating:<16}{target_str:>10}"
                )

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_insider_activity(ticker: str) -> List[TextContent]:
        """Get insider trading activity from Finviz.
        Shows recent insider buys/sells — useful for gauging management conviction.

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
        """Get recent news headlines for a stock.

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
