"""
Price History Tools — annual high/low/average from Yahoo Finance.

Data source: Yahoo Finance via yfinance (free, no API key).
"""

import logging
from typing import List

from mcp.types import TextContent

from ..clients.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)
yf_client = YFinanceClient()


def register_price_history_tools(server):
    """Register price history tools."""

    @server.tool()
    def get_annual_price_history(
        ticker: str,
        years: int = 11,
    ) -> List[TextContent]:
        """Get annual high, low, and average close prices for a stock.
        Returns one row per calendar year with the highest intraday price,
        lowest intraday price, and mean daily closing price.

        Data source: Yahoo Finance (free, no API key). Prices are
        split-adjusted.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL", "MSFT").
            years: Number of years of history to fetch (default 11).
        """
        try:
            data = yf_client.get_annual_price_history(ticker, years=years)

            if not data:
                return [TextContent(
                    type="text",
                    text=f"No price history found for {ticker.upper()}. "
                         f"Check that the ticker symbol is correct.",
                )]

            rows = data["rows"]

            lines = [
                f"Annual Price History: {ticker.upper()}",
                f"Source: Yahoo Finance (split-adjusted)",
                "=" * 52,
                "",
                f"{'Year':<6}{'High':>14}{'Low':>14}{'Avg Close':>14}",
                "-" * 52,
            ]

            for r in rows:
                lines.append(
                    f"{r['year']:<6}"
                    f"{'${:,.2f}'.format(r['high']):>14}"
                    f"{'${:,.2f}'.format(r['low']):>14}"
                    f"{'${:,.2f}'.format(r['avg_close']):>14}"
                )

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_annual_price_history error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
