"""
SEC Filing Tools
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.edgar_client import EdgarClient

logger = logging.getLogger(__name__)
edgar = EdgarClient()


def register_sec_tools(server):
    """Register SEC/EDGAR filing tools."""

    @server.tool()
    def get_sec_filings(
        ticker: str,
        form_type: str = "",
        max_results: int = 15,
    ) -> List[TextContent]:
        """List recent SEC filings for a company.

        Args:
            ticker: Stock ticker symbol.
            form_type: Filter by form type. Common options:
                "10-K"  — Annual report (full financials, risk factors, MD&A)
                "10-Q"  — Quarterly report
                "8-K"   — Current report (material events)
                "DEF 14A" — Proxy statement (executive comp, governance)
                "4"     — Insider trading (Form 4)
                "S-1"   — IPO registration
                ""      — All forms (default)
            max_results: Number of filings to return (default 15).
        """
        try:
            form_types = [form_type] if form_type else None
            filings = edgar.get_filings(
                ticker, form_types=form_types, max_results=max_results
            )

            if not filings:
                return [TextContent(
                    type="text",
                    text=f"No SEC filings found for {ticker.upper()}"
                         + (f" (form type: {form_type})" if form_type else ""),
                )]

            lines = [
                f"SEC Filings for {ticker.upper()}"
                + (f" — Form {form_type}" if form_type else ""),
                "=" * 60,
                "",
            ]

            for f in filings:
                lines.append(
                    f"▸ {f['form']} — {f['date']}"
                )
                if f.get("description"):
                    lines.append(f"  {f['description']}")
                lines.append(f"  {f['url']}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_sec_filings error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_filing_text(
        ticker: str,
        form_type: str = "10-K",
        max_chars: int = 15000,
    ) -> List[TextContent]:
        """Fetch and return the text content of the most recent filing.
        Useful for reading risk factors, MD&A, business descriptions.

        Args:
            ticker: Stock ticker symbol.
            form_type: Form to fetch — "10-K", "10-Q", "8-K", etc.
            max_chars: Max characters to return (default 15000).
                       Larger values give more context but use more tokens.
        """
        try:
            result = edgar.get_filing_text(
                ticker, form_type=form_type, max_chars=max_chars
            )

            if not result:
                return [TextContent(
                    type="text",
                    text=f"Could not retrieve {form_type} for {ticker.upper()}. "
                         f"The company may not have filed this form type.",
                )]

            lines = [
                f"SEC Filing: {result['form']} for {ticker.upper()}",
                f"Filed: {result['date']}",
                f"Source: {result['url']}",
            ]
            if result.get("truncated"):
                lines.append(
                    f"(Truncated to {max_chars:,} characters — "
                    f"increase max_chars for more)"
                )
            lines.extend(["", "=" * 60, "", result["text"]])

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_filing_text error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_financial_history(
        ticker: str,
        metric: str = "Revenues",
        periods: int = 8,
    ) -> List[TextContent]:
        """Get historical financial data from SEC XBRL filings.
        Returns actual reported values — not estimates or scraped data.

        Args:
            ticker: Stock ticker symbol.
            metric: XBRL concept name. Common value-investing metrics:
                "Revenues" — Total revenue
                "NetIncomeLoss" — Net income
                "EarningsPerShareBasic" — Basic EPS (use unit "USD/shares")
                "EarningsPerShareDiluted" — Diluted EPS (use unit "USD/shares")
                "Assets" — Total assets
                "Liabilities" — Total liabilities
                "StockholdersEquity" — Shareholder equity
                "OperatingIncomeLoss" — Operating income
                "CashAndCashEquivalentsAtCarryingValue" — Cash on hand
                "LongTermDebt" — Long-term debt
                "CommonStockSharesOutstanding" — Shares outstanding (unit "shares")
                "DividendsCommonStockCash" — Cash dividends paid
            periods: Number of recent periods to show (default 8).
        """
        try:
            # Determine unit based on metric
            if "PerShare" in metric:
                unit = "USD/shares"
            elif "Shares" in metric:
                unit = "shares"
            else:
                unit = "USD"

            data = edgar.get_financial_metric(
                ticker, concept=metric, unit=unit, periods=periods
            )

            if not data:
                return [TextContent(
                    type="text",
                    text=f"No XBRL data found for {ticker.upper()} — {metric}.\n"
                         f"Try a different metric name or check that the company "
                         f"files in US-GAAP format.",
                )]

            lines = [
                f"Financial History: {ticker.upper()} — {metric}",
                f"Source: SEC EDGAR XBRL (reported values)",
                "=" * 55,
                "",
                f"{'Period End':<14}{'Form':<8}{'FY':<6}{'Value':>18}",
                "-" * 55,
            ]

            for entry in data:
                val = entry.get("val", 0)
                # Format large numbers
                if unit == "USD" and abs(val) >= 1_000_000:
                    val_str = f"${val / 1_000_000:,.1f}M"
                elif unit == "USD":
                    val_str = f"${val:,.0f}"
                elif unit == "USD/shares":
                    val_str = f"${val:.2f}"
                elif unit == "shares":
                    val_str = f"{val / 1_000_000:,.1f}M"
                else:
                    val_str = f"{val:,.0f}"

                lines.append(
                    f"{entry.get('end', '?'):<14}"
                    f"{entry.get('form', '?'):<8}"
                    f"{entry.get('fy', '?'):<6}"
                    f"{val_str:>18}"
                )

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_financial_history error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_insider_filings(
        ticker: str, max_results: int = 15
    ) -> List[TextContent]:
        """Get insider trading SEC filings (Form 3, 4, 5) for a company.

        Args:
            ticker: Stock ticker symbol.
            max_results: Number of filings to return.
        """
        try:
            filings = edgar.get_filings(
                ticker, form_types=["3", "4", "5"], max_results=max_results
            )

            if not filings:
                return [TextContent(
                    type="text",
                    text=f"No insider filings found for {ticker.upper()}",
                )]

            lines = [
                f"Insider Filings (Form 3/4/5) for {ticker.upper()}",
                "=" * 60,
                "",
            ]
            for f in filings:
                lines.append(f"▸ Form {f['form']} — {f['date']}")
                if f.get("description"):
                    lines.append(f"  {f['description']}")
                lines.append(f"  {f['url']}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]
