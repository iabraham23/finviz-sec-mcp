"""
Individual Stock Fundamentals Tools
Priority 2 — 90+ data points per ticker for deep value analysis.
"""

import logging
from typing import List, Optional
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()

# Fields grouped by value-investing relevance
VALUE_FIELDS = [
    "P/E", "Forward P/E", "PEG", "P/S", "P/B", "P/C", "P/FCF",
    "EPS (ttm)", "EPS next Y", "EPS next Q", "EPS past 5Y", "EPS next 5Y",
    "EPS Q/Q",
]
PROFITABILITY_FIELDS = [
    "ROE", "ROA", "ROI", "Gross Margin", "Oper. Margin", "Profit Margin",
]
BALANCE_SHEET_FIELDS = [
    "Market Cap", "Income", "Sales", "Book/sh", "Cash/sh",
    "Debt/Eq", "LT Debt/Eq", "Current Ratio", "Quick Ratio",
]
DIVIDEND_FIELDS = [
    "Dividend %", "Dividend", "Payout",
]
OWNERSHIP_FIELDS = [
    "Insider Own", "Insider Trans", "Inst Own", "Inst Trans",
    "Short Float", "Short Ratio", "Short Interest",
]
TECHNICAL_FIELDS = [
    "Price", "Change", "Volume", "Avg Volume", "Rel Volume",
    "Beta", "RSI (14)", "52W High", "52W Low",
    "SMA20", "SMA50", "SMA200", "ATR",
]


def _format_stock_section(data: dict, title: str, fields: list) -> List[str]:
    """Format a section of stock data."""
    lines = [f"  {title}:"]
    parts = []
    for f in fields:
        val = data.get(f, "-")
        if val and val != "-":
            parts.append(f"{f}: {val}")
    for i in range(0, len(parts), 3):
        chunk = parts[i : i + 3]
        lines.append(f"    {' | '.join(chunk)}")
    return lines


def register_fundamentals_tools(server):
    """Register fundamental analysis tools."""

    @server.tool()
    def get_stock_fundamentals(ticker: str) -> List[TextContent]:
        """Get comprehensive fundamental data for a stock (90+ metrics).
        Organized into value-relevant sections for quick analysis.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL", "BRK-B").
        """
        try:
            data = client.get_stock(ticker)
            if not data:
                return [TextContent(type="text", text=f"No data found for {ticker}")]

            company = data.get("Company", ticker)
            sector = data.get("Sector", "?")
            industry = data.get("Industry", "?")

            lines = [
                f"{ticker.upper()} — {company}",
                f"Sector: {sector} | Industry: {industry}",
                "=" * 60,
            ]

            lines.extend(_format_stock_section(data, "Valuation", VALUE_FIELDS))
            lines.append("")
            lines.extend(_format_stock_section(data, "Profitability", PROFITABILITY_FIELDS))
            lines.append("")
            lines.extend(_format_stock_section(data, "Balance Sheet", BALANCE_SHEET_FIELDS))
            lines.append("")
            lines.extend(_format_stock_section(data, "Dividends", DIVIDEND_FIELDS))
            lines.append("")
            lines.extend(_format_stock_section(data, "Ownership & Short Interest", OWNERSHIP_FIELDS))
            lines.append("")
            lines.extend(_format_stock_section(data, "Price & Technical", TECHNICAL_FIELDS))

            # Include target price and analyst rec
            target = data.get("Target Price", "-")
            recom = data.get("Recom", "-")
            earnings = data.get("Earnings", "-")
            lines.append("")
            lines.append(f"  Analyst Target: {target} | Recommendation: {recom} | Next Earnings: {earnings}")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_stock_fundamentals error: {e}")
            return [TextContent(type="text", text=f"Error fetching {ticker}: {e}")]

    @server.tool()
    def compare_stocks(tickers: str, metrics: str = "") -> List[TextContent]:
        """Compare fundamental metrics across multiple stocks side-by-side.

        Args:
            tickers: Comma-separated tickers, e.g. "AAPL,MSFT,GOOGL"
            metrics: Optional comma-separated metric names to compare.
                     If empty, uses default value-investing metrics:
                     P/E, P/B, ROE, Profit Margin, Debt/Eq, Dividend %, EPS next Y
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            if not ticker_list:
                return [TextContent(type="text", text="Please provide at least one ticker.")]

            if metrics:
                metric_list = [m.strip() for m in metrics.split(",")]
            else:
                metric_list = [
                    "P/E", "Forward P/E", "P/B", "P/FCF", "PEG",
                    "ROE", "ROA", "Profit Margin", "Oper. Margin",
                    "Debt/Eq", "Current Ratio",
                    "Dividend %", "Payout",
                    "EPS (ttm)", "EPS next Y", "EPS past 5Y",
                    "Market Cap", "Price",
                ]

            stocks = client.get_multiple_stocks(ticker_list)

            # Build comparison table
            lines = [
                f"Stock Comparison: {', '.join(ticker_list)}",
                "=" * 70,
                "",
            ]

            # Header
            header = f"{'Metric':<22}" + "".join(
                f"{t:<14}" for t in ticker_list
            )
            lines.append(header)
            lines.append("-" * len(header))

            for metric in metric_list:
                row = f"{metric:<22}"
                for stock in stocks:
                    if "error" in stock:
                        row += f"{'ERR':<14}"
                    else:
                        val = stock.get(metric, "-")
                        row += f"{str(val):<14}"
                lines.append(row)

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"compare_stocks error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
