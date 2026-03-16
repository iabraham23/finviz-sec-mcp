"""
SEC EDGAR Tools — historical financial data and filing access.

Data source: SEC EDGAR public API (free, no key required).
All financial values are actual reported figures from XBRL-tagged filings.

Tool selection guide
────────────────────
get_financial_history  — Historical annual OR quarterly series for ONE company.
                         Use period_type="annual" for clean year-over-year models.
get_financial_ttm      — Trailing twelve months for one or more companies.
                         Best for up-to-date income statement / cash flow values.
compare_financials     — Same metric across MULTIPLE companies for a given year.
                         Handles non-December fiscal year ends automatically.
get_filing_text        — Full text of a specific filing (10-K MD&A, risk factors, etc.)
get_sec_filings        — List of recent filings with EDGAR links.
get_insider_filings    — Form 3/4/5 insider transaction filings.

For current-snapshot fundamentals (ratios, price, etc.) use the Finviz tools:
get_stock_fundamentals, compare_stocks, get_analyst_ratings, get_insider_activity.
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
        """List recent SEC filings for a company with EDGAR links.
        Use this to find filing dates and document URLs before calling
        get_filing_text. Data source: SEC EDGAR submissions API.

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
        """Fetch and return the text content of the most recent SEC filing.
        Strips iXBRL markup and skips directly to the first section heading
        (Item 1, Item 1A, Item 7, etc.) for clean readable text.
        Useful for reading risk factors, MD&A, and business descriptions.
        For structured financial data use get_financial_history instead.

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
        period_type: str = "annual",
    ) -> List[TextContent]:
        """Get historical financial data from SEC XBRL filings.
        Returns actual reported values — not estimates or scraped data.

        Args:
            ticker: Stock ticker symbol.
            metric: XBRL concept name. Common value-investing metrics:
                "Revenues" — Total revenue
                "NetIncomeLoss" — Net income
                "GrossProfit" — Gross profit
                "OperatingIncomeLoss" — Operating income
                "EarningsPerShareBasic" — Basic EPS (use unit "USD/shares")
                "EarningsPerShareDiluted" — Diluted EPS (use unit "USD/shares")
                "Assets" — Total assets
                "Liabilities" — Total liabilities
                "StockholdersEquity" — Shareholder equity
                "CashAndCashEquivalentsAtCarryingValue" — Cash on hand
                "LongTermDebt" — Long-term debt
                "CommonStockSharesOutstanding" — Shares outstanding (unit "shares")
                "ResearchAndDevelopmentExpense" — R&D expense
                "SellingGeneralAndAdministrativeExpense" — SG&A expense
                "InterestExpense" — Interest expense
                "IncomeTaxExpenseBenefit" — Income tax expense
                "DepreciationDepletionAndAmortization" — D&A
                "CapitalExpenditure" — Capital expenditures
                "NetCashProvidedByUsedInOperatingActivities" — Operating cash flow
            periods: Number of recent periods to show (default 8).
            period_type: Controls which filings are included:
                "annual"    — 10-K only. Clean year-over-year series.
                              RECOMMENDED for financial modeling.
                "quarterly" — 10-Q only. Clean quarter-over-quarter series,
                              useful for recent trend analysis.
                "all"       — Both 10-K and 10-Q mixed (legacy behaviour,
                              not recommended for modeling).
        """
        try:
            # Determine unit based on metric
            if "PerShare" in metric:
                unit = "USD/shares"
            elif "Shares" in metric:
                unit = "shares"
            else:
                unit = "USD"

            # Map period_type to form_types filter
            form_map = {
                "annual":    ["10-K"],
                "quarterly": ["10-Q"],
                "all":       None,   # None → both
            }
            form_types = form_map.get(period_type, ["10-K"])

            data = edgar.get_financial_metric(
                ticker, concept=metric, unit=unit,
                periods=periods, form_types=form_types,
            )

            if not data:
                alt_hint = ""
                if period_type != "all":
                    alt_hint = (
                        f"\nTip: Try period_type='all' to search both "
                        f"annual and quarterly filings."
                    )
                return [TextContent(
                    type="text",
                    text=f"No XBRL data found for {ticker.upper()} — {metric} "
                         f"({period_type} filings).\n"
                         f"Try a different metric name or check that the company "
                         f"files in US-GAAP format.{alt_hint}",
                )]

            # Check if a fallback concept was used
            concept_used = data[0].get("concept_used", metric)
            fallback_note = ""
            if concept_used != metric:
                fallback_note = (
                    f"Note: '{metric}' not found. Using '{concept_used}' instead.\n"
                )

            period_label = {
                "annual": "Annual (10-K)",
                "quarterly": "Quarterly (10-Q)",
                "all": "Annual + Quarterly",
            }.get(period_type, period_type)

            lines = [
                f"Financial History: {ticker.upper()} — {metric}",
                f"Series: {period_label} | Source: SEC EDGAR XBRL",
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
                    f"{str(entry.get('fy', '?')):<6}"
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
        """Get insider trading SEC filings (Form 3, 4, 5) with EDGAR links.
        Returns filing dates, descriptions, and direct document URLs.
        For a human-readable summary of recent buys/sells with dollar values,
        use get_insider_activity (Finviz) instead.

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

        Companies with non-December fiscal year ends are automatically
        handled via a per-company fallback — no ticker is silently dropped.

        Args:
            tickers: Comma-separated ticker symbols, e.g. "AAPL,MSFT,GOOGL".
            metric: XBRL concept name. Common metrics:
                "Revenues" — Total revenue
                "NetIncomeLoss" — Net income
                "GrossProfit" — Gross profit
                "OperatingIncomeLoss" — Operating income
                "EarningsPerShareBasic" — Basic EPS
                "EarningsPerShareDiluted" — Diluted EPS
                "Assets" — Total assets
                "Liabilities" — Total liabilities
                "StockholdersEquity" — Shareholder equity
                "CashAndCashEquivalentsAtCarryingValue" — Cash on hand
                "LongTermDebt" — Long-term debt
                "CommonStockSharesOutstanding" — Shares outstanding
                "ResearchAndDevelopmentExpense" — R&D expense
                "SellingGeneralAndAdministrativeExpense" — SG&A expense
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

            # Check for concept fallback (use first calendar-period result for label)
            cal_results = [r for r in results if not r.get("fiscal_year_note")]
            concept_used = (cal_results or results)[0].get("concept_used", metric)
            fallback_note = ""
            if concept_used != metric:
                fallback_note = (
                    f"Note: '{metric}' not found. "
                    f"Using '{concept_used}' instead.\n"
                )

            period_label = f"Q{quarter} {year}" if qtr else str(year)
            lines = [
                f"Financial Comparison: {metric} — {period_label}",
                f"Source: SEC EDGAR XBRL",
            ]
            if fallback_note:
                lines.append(fallback_note)
            lines.extend([
                "=" * 65,
                "",
                f"{'Ticker':<10}{'Company':<30}{'Value':>18}  {'Period End'}",
                "-" * 65,
            ])

            # Sort by value descending for easy comparison
            results.sort(
                key=lambda x: x.get("val") or 0, reverse=True,
            )

            fiscal_year_notes = []
            for r in results:
                val = r.get("val")
                val_str = _format_usd(val, unit) if val is not None else "N/A"
                name = r.get("entity_name", r.get("ticker", ""))
                if len(name) > 28:
                    name = name[:25] + "..."
                end_date = r.get("end", "")
                # Flag non-standard fiscal year entries
                fy_marker = " *" if r.get("fiscal_year_note") else ""
                lines.append(
                    f"{r['ticker']:<10}{name:<30}{val_str:>18}  {end_date}{fy_marker}"
                )
                if r.get("fiscal_year_note"):
                    fiscal_year_notes.append(r["ticker"])

            if fiscal_year_notes:
                lines.extend([
                    "",
                    f"* {', '.join(fiscal_year_notes)}: non-December fiscal year — "
                    f"value shown is from the fiscal year ending closest to {year}.",
                ])

            # Note any tickers completely absent from XBRL data
            found_tickers = {r["ticker"] for r in results}
            missing = [t for t in ticker_list if t not in found_tickers]
            if missing:
                lines.extend([
                    "",
                    f"Not found in XBRL data: {', '.join(missing)}",
                    "(Company may use IFRS taxonomy, have no SEC filings, "
                    "or not yet filed for this period.)",
                ])

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"compare_financials error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_financial_ttm(
        tickers: str,
        metric: str = "Revenues",
    ) -> List[TextContent]:
        """Get Trailing Twelve Months (TTM) value for one or more companies.
        Sums the four most recent quarterly filings for income statement /
        cash flow metrics, or returns the latest quarter for balance sheet items.
        Useful for up-to-date analysis without waiting for the next annual filing.

        Args:
            tickers: Comma-separated ticker symbols, e.g. "AAPL,MSFT,GOOGL".
            metric: XBRL concept name. Income statement / cash flow metrics
                    (summed over 4 quarters):
                "Revenues" — Total revenue
                "NetIncomeLoss" — Net income
                "GrossProfit" — Gross profit
                "OperatingIncomeLoss" — Operating income
                "ResearchAndDevelopmentExpense" — R&D expense
                "SellingGeneralAndAdministrativeExpense" — SG&A
                "InterestExpense" — Interest expense
                "IncomeTaxExpenseBenefit" — Income tax
                "DepreciationDepletionAndAmortization" — D&A
                "CapitalExpenditure" — CapEx
                "NetCashProvidedByUsedInOperatingActivities" — Operating FCF
                Balance sheet metrics (latest quarter, no summing):
                "Assets", "Liabilities", "StockholdersEquity",
                "CashAndCashEquivalentsAtCarryingValue", "LongTermDebt"
        """
        try:
            ticker_list = [
                t.strip().upper() for t in tickers.split(",") if t.strip()
            ]
            if not ticker_list:
                return [TextContent(type="text", text="Please provide at least one ticker.")]

            # Determine unit based on metric
            if "PerShare" in metric:
                unit = "USD/shares"
            elif "Shares" in metric:
                unit = "shares"
            else:
                unit = "USD"

            lines = [
                f"TTM Analysis: {metric}",
                f"Source: SEC EDGAR XBRL (4 most recent quarters summed)",
                "=" * 65,
                "",
                f"{'Ticker':<10}{'TTM Value':>20}  {'As of':<14}{'Periods'}",
                "-" * 65,
            ]

            any_found = False
            for ticker in ticker_list:
                result = edgar.get_financial_ttm(
                    ticker, concept=metric, unit=unit,
                )
                if not result:
                    lines.append(f"{ticker:<10}{'N/A':>20}  {'—':<14}")
                    continue

                any_found = True
                val_str = _format_usd(result["ttm_val"], unit)
                end_date = result.get("latest_quarter_end", "?")
                periods = result.get("periods_used", "?")
                is_instant = result.get("is_instantaneous", False)
                label = "latest" if is_instant else f"{periods}Q"

                line = f"{ticker:<10}{val_str:>20}  {end_date:<14}{label}"
                if result.get("note"):
                    line += f"  [{result['note']}]"
                lines.append(line)

            if not any_found:
                return [TextContent(
                    type="text",
                    text=f"No TTM data found for {metric}.\n"
                         f"Check that tickers file in US-GAAP format and "
                         f"that the metric name is correct.",
                )]

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_financial_ttm error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
