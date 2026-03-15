"""
SEC Filing Tools
"""

import logging
from datetime import date
from typing import List
from mcp.types import TextContent

from ..clients.edgar_client import EdgarClient

logger = logging.getLogger(__name__)
edgar = EdgarClient()


def _format_usd(val: float, unit: str) -> str:
    """Format a numeric value with appropriate unit suffix."""
    if unit == "USD" and abs(val) >= 1_000_000_000:
        return f"${val / 1_000_000_000:,.2f}B"
    if unit == "USD" and abs(val) >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    if unit == "USD":
        return f"${val:,.0f}"
    if unit == "USD/shares":
        return f"${val:.2f}"
    if unit == "shares" and abs(val) >= 1_000_000:
        return f"{val / 1_000_000:,.1f}M"
    return f"{val:,.0f}"


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

            # Check if a fallback concept was used
            concept_used = data[0].get("concept_used", metric)
            fallback_note = ""
            if concept_used != metric:
                fallback_note = (
                    f"\nNote: '{metric}' not found in XBRL data. "
                    f"Using '{concept_used}' instead.\n"
                )

            lines = [
                f"Financial History: {ticker.upper()} — {metric}",
                f"Source: SEC EDGAR XBRL (reported values)",
            ]
            if fallback_note:
                lines.append(fallback_note)
            lines.extend([
                "=" * 55,
                "",
                f"{'Period End':<14}{'Form':<8}{'FY':<6}{'Value':>18}",
                "-" * 55,
            ])

            for entry in data:
                val = entry.get("val", 0)
                val_str = _format_usd(val, unit)

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

    @server.tool()
    def compare_financials(
        tickers: str,
        metric: str = "Revenues",
        year: int = 0,
        quarter: int = 0,
    ) -> List[TextContent]:
        """Compare a financial metric across multiple companies using
        SEC XBRL data. Uses the XBRL frames endpoint — one API call
        retrieves the metric for all companies, so this is very efficient.
        Returns actual reported values from SEC filings.

        Args:
            tickers: Comma-separated ticker symbols, e.g. "AAPL,MSFT,GOOGL".
            metric: XBRL concept name. Common metrics:
                "Revenues" — Total revenue
                "NetIncomeLoss" — Net income
                "EarningsPerShareBasic" — Basic EPS
                "EarningsPerShareDiluted" — Diluted EPS
                "Assets" — Total assets
                "Liabilities" — Total liabilities
                "StockholdersEquity" — Shareholder equity
                "OperatingIncomeLoss" — Operating income
                "CashAndCashEquivalentsAtCarryingValue" — Cash on hand
                "LongTermDebt" — Long-term debt
                "CommonStockSharesOutstanding" — Shares outstanding
            year: Calendar year to compare (e.g. 2024). Defaults to
                  previous year if not specified.
            quarter: Optional quarter (1-4). 0 = full year (default).
        """
        try:
            ticker_list = [
                t.strip().upper() for t in tickers.split(",") if t.strip()
            ]
            if not ticker_list:
                return [TextContent(
                    type="text", text="Please provide at least one ticker."
                )]

            # Default to previous calendar year (most likely to have data)
            if year == 0:
                year = date.today().year - 1

            # Determine unit based on metric
            if "PerShare" in metric:
                unit = "USD/shares"
            elif "Shares" in metric:
                unit = "shares"
            else:
                unit = "USD"

            qtr = quarter if quarter in (1, 2, 3, 4) else None

            results = edgar.compare_metric_across_companies(
                ticker_list,
                concept=metric,
                year=year,
                quarter=qtr,
                unit=unit,
            )

            if not results:
                period_label = f"Q{quarter} " if qtr else ""
                return [TextContent(
                    type="text",
                    text=f"No XBRL data found for {metric} "
                         f"({period_label}{year}).\n"
                         f"Data may not yet be available for this period, "
                         f"or try a different year.",
                )]

            # Check for fallback
            concept_used = results[0].get("concept_used", metric)
            period_used = results[0].get("period", "")
            fallback_note = ""
            if concept_used != metric:
                fallback_note = (
                    f"\nNote: '{metric}' not found. "
                    f"Using '{concept_used}' instead.\n"
                )

            period_label = f"Q{quarter} {year}" if qtr else str(year)
            lines = [
                f"Financial Comparison: {metric} — {period_label}",
                f"Source: SEC EDGAR XBRL frames ({period_used})",
            ]
            if fallback_note:
                lines.append(fallback_note)
            lines.extend([
                "=" * 60,
                "",
                f"{'Ticker':<10}{'Company':<30}{'Value':>18}",
                "-" * 60,
            ])

            # Sort by value descending for easy comparison
            results.sort(
                key=lambda x: x.get("val") or 0, reverse=True,
            )

            for r in results:
                val = r.get("val")
                val_str = _format_usd(val, unit) if val is not None else "N/A"
                name = r.get("entity_name", "")
                # Truncate long names
                if len(name) > 28:
                    name = name[:25] + "..."
                lines.append(
                    f"{r['ticker']:<10}{name:<30}{val_str:>18}"
                )

            # Note any tickers that weren't found
            found_tickers = {r["ticker"] for r in results}
            missing = [t for t in ticker_list if t not in found_tickers]
            if missing:
                lines.extend([
                    "",
                    f"Not found in XBRL data: {', '.join(missing)}",
                    "(Company may use a different fiscal year-end, "
                    "IFRS taxonomy, or not yet filed.)",
                ])

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"compare_financials error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
