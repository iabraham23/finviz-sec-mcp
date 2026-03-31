"""
SEC EDGAR Tools — historical financial data and filing access.

Data source: SEC EDGAR public API via edgartools library (free, no key required).
All financial values are actual reported figures from XBRL-tagged filings.

Tool selection guide
────────────────────
get_financial_history  — Historical annual OR quarterly series for ONE company.
                         Use period_type="annual" for clean year-over-year models.
get_financial_ttm      — Trailing twelve months for one or more companies.
                         Best for up-to-date income statement / cash flow values.
compare_financials     — Same metric across MULTIPLE companies for a given year.
                         Handles non-December fiscal year ends automatically.
get_financial_snapshot  — Full income statement, balance sheet, and cash flow
                         from the latest filing. Best starting point for analysis.
get_per_share_fundamentals — Historical BV/share, TBV/share, Rev/share, OCF/share,
                         EPS, diluted shares. Replaces SimFin for valuation inputs.
get_filing_text        — Full text of a specific filing (10-K MD&A, risk factors, etc.)
get_sec_filings        — List of recent filings with EDGAR links.
get_insider_filings    — Form 3/4/5 insider transaction filings with structured data.

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
    if val is None:
        return "N/A"
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
        get_filing_text. Data source: SEC EDGAR via edgartools.

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
        sections: str = "Item 7,Item 1A",
        max_chars_per_section: int = 8000,
    ) -> List[TextContent]:
        """Fetch specific narrative sections from the most recent SEC filing.
        For 10-K and 10-Q filings, uses edgartools' structured TenK/TenQ
        objects to pull named items directly — no iXBRL overhead, no
        wasted character budget on table-of-contents boilerplate.
        For 20-F filings, uses edgartools markdown extraction from the
        primary filing HTML and slices by 20-F item headings.
        For other form types (8-K, etc.), falls back to full-text extraction.

        Args:
            ticker: Stock ticker symbol.
            form_type: Form to fetch — "10-K", "10-Q", "8-K", etc.
            sections: Comma-separated list of items to retrieve.
                Default "Item 7,Item 1A" returns MD&A + Risk Factors for
                10-K / 10-Q. For 20-F, useful sections include:
                "Item 3.D", "Item 4", "Item 5", "Item 18", plus aliases
                like "risk_factors", "business", "mda", "financial_statements".
                Supported formats:
                  Full:     "Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8"
                  Short:    "1", "1A", "7", "7A"
                  Aliases:  "mda", "risk_factors", "business"
                Pass sections="" to get Item 7 + Item 1A (same as default).
                Use get_sec_filings first to confirm available items.
            max_chars_per_section: Max characters per section (default 8000).
                Each section is truncated independently.
        """
        try:
            # Parse sections list; fall back to defaults
            section_list = [s.strip() for s in sections.split(",") if s.strip()]
            if not section_list:
                section_list = ["Item 7", "Item 1A"]

            result = edgar.get_filing_sections(
                ticker,
                form_type=form_type,
                sections=section_list,
                max_chars_per_section=max_chars_per_section,
            )

            if not result:
                return [TextContent(
                    type="text",
                    text=f"Could not retrieve {form_type} for {ticker.upper()}. "
                         f"The company may not have filed this form type.",
                )]

            # Section label maps — 10-K and 10-Q use different item numbers
            # for the same content (e.g. MD&A is Item 7 in 10-K, Item 2 in 10-Q).
            _10K_LABELS = {
                "Item 1":  "Business",
                "Item 1A": "Risk Factors",
                "Item 1B": "Unresolved Staff Comments",
                "Item 2":  "Properties",
                "Item 3":  "Legal Proceedings",
                "Item 7":  "Management's Discussion and Analysis",
                "Item 7A": "Quantitative and Qualitative Disclosures",
                "Item 8":  "Financial Statements",
                "Item 9A": "Controls and Procedures",
            }
            _10Q_LABELS = {
                "Item 1":  "Financial Statements",
                "Item 1A": "Risk Factors",
                "Item 2":  "Management's Discussion and Analysis",
                "Item 3":  "Quantitative and Qualitative Disclosures",
                "Item 4":  "Controls and Procedures",
            }
            _20F_LABELS = {
                "Item 3.D": "Risk Factors",
                "Item 4": "Information on the Company",
                "Item 5": "Operating and Financial Review and Prospects",
                "Item 17": "Financial Statements",
                "Item 18": "Financial Statements",
            }
            filing_form = result.get("form", form_type)
            if "10-Q" in filing_form:
                _SECTION_LABELS = _10Q_LABELS
            elif "20-F" in filing_form:
                _SECTION_LABELS = _20F_LABELS
            else:
                _SECTION_LABELS = _10K_LABELS

            method = result.get("method", "structured")
            lines = [
                f"SEC Filing: {result['form']} for {ticker.upper()}",
                f"Filed: {result['date']}",
                f"Source: {result['url']}",
            ]

            extracted = result.get("sections", {})
            available = result.get("available_items", [])

            if method in {"structured", "markdown_sections"}:
                lines.append(
                    f"Sections: {', '.join(extracted.keys()) or 'none found'}"
                )
                if available:
                    lines.append(
                        f"Available items: {', '.join(str(i) for i in available)}"
                    )
            lines.append("=" * 60)

            if method == "raw_text":
                # Fallback path — single text blob
                lines.extend(["", extracted.get("text", "(no text)")])
            else:
                for section_name, text in extracted.items():
                    label = _SECTION_LABELS.get(section_name, section_name)
                    lines.extend([
                        "",
                        f"── {section_name}: {label} ──",
                        "",
                        text,
                    ])

                if not extracted:
                    found_names = ", ".join(str(i) for i in available) if available else "unknown"
                    lines.extend([
                        "",
                        f"None of the requested sections ({', '.join(section_list)}) "
                        f"were found in this filing.",
                        f"Available items: {found_names}",
                    ])

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
                "Goodwill" — Goodwill (balance sheet)
                "IntangibleAssetsNetExcludingGoodwill" — Intangible assets net of goodwill
                "WeightedAverageNumberOfDilutedSharesOutstanding" — Diluted shares (unit "shares")
            periods: Number of recent periods to show (default 8).
            period_type: Controls which filings are included:
                "annual"    — Annual filings (10-K / 20-F / 40-F).
                              Clean year-over-year series.
                              RECOMMENDED for financial modeling.
                "quarterly" — 10-Q only. Clean quarter-over-quarter series,
                              useful for recent trend analysis.
                "interim"   — Interim filings (10-Q / 6-K). Includes
                              foreign private issuer interim XBRL when present.
                              May include both ~3-month and ~6-month periods.
                "all"       — Annual + interim filings mixed
                              (not recommended for modeling).
        """
        try:
            # Determine unit based on metric
            if "PerShare" in metric:
                unit = "USD/shares"
            elif "Shares" in metric or "ShareOutstanding" in metric:
                unit = "shares"
            else:
                unit = "USD"

            # Map period_type to form_types filter
            form_map = {
                "annual":    ["10-K", "20-F", "40-F"],
                "quarterly": ["10-Q"],
                "interim":   ["10-Q", "6-K"],
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
                        f"\nTip: Try period_type='interim' or period_type='all' "
                        f"to search 10-Q and 6-K filings as well."
                    )
                return [TextContent(
                    type="text",
                    text=f"No XBRL data found for {ticker.upper()} — {metric} "
                         f"({period_type} filings).\n"
                         f"Try a different metric name or check that the company "
                         f"files XBRL-tagged annual/quarterly reports.{alt_hint}",
                )]

            # Check if a fallback concept was used
            concept_used = data[0].get("concept_used", metric)
            fallback_note = ""
            if concept_used != metric:
                fallback_note = (
                    f"Note: '{metric}' not found. Using '{concept_used}' instead.\n"
                )

            period_label = {
                "annual": "Annual (10-K / 20-F / 40-F)",
                "quarterly": "Quarterly (10-Q)",
                "interim": "Interim (10-Q / 6-K)",
                "all": "Annual + Interim",
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
        """Get insider trading SEC filings (Form 3, 4, 5) with structured data.
        Returns filing dates, insider names, positions, trade details,
        and direct EDGAR links. Powered by edgartools' Form4 parser.

        For a human-readable summary of recent buys/sells with dollar values,
        use get_insider_activity (Finviz) instead.

        Args:
            ticker: Stock ticker symbol.
            max_results: Number of filings to return.
        """
        try:
            filings = edgar.get_insider_filings_detailed(
                ticker, max_results=max_results
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
                header = f"▸ Form {f['form']} — {f['date']}"
                if f.get("insider_name"):
                    header += f" | {f['insider_name']}"
                if f.get("position"):
                    header += f" ({f['position']})"
                lines.append(header)

                details = []
                if f.get("activity"):
                    details.append(f"Activity: {f['activity']}")
                if f.get("net_change") is not None and f["net_change"] != 0:
                    details.append(f"Net shares: {f['net_change']:+,.0f}")
                if f.get("net_value") is not None and f["net_value"] != 0:
                    details.append(f"Net value: ${f['net_value']:,.0f}")
                if f.get("remaining_shares") is not None:
                    details.append(f"Remaining: {f['remaining_shares']:,.0f}")

                if details:
                    lines.append(f"  {' | '.join(details)}")

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
        SEC XBRL data. Returns actual reported values from SEC filings.

        Companies with non-December fiscal year ends are automatically
        handled — no ticker is silently dropped.

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
            elif "Shares" in metric or "ShareOutstanding" in metric:
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

            # Check for concept fallback
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

            # Note any tickers completely absent
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
            elif "Shares" in metric or "ShareOutstanding" in metric:
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

    @server.tool()
    def get_financial_snapshot(
        ticker: str,
    ) -> List[TextContent]:
        """Get a complete financial snapshot from the latest SEC filing:
        income statement, balance sheet, and cash flow statement with
        multi-period comparison. Also includes quick-access metrics
        (revenue, net income, FCF, etc.).

        This is the best starting point for company financial analysis.
        Returns actual XBRL-tagged data from SEC filings — not estimates.
        Powered by edgartools' Financials API.

        Args:
            ticker: Stock ticker symbol.
        """
        try:
            data = edgar.get_financial_statements(ticker)

            if not data:
                return [TextContent(
                    type="text",
                    text=f"Could not retrieve financial statements for {ticker.upper()}. "
                         f"The company may not file in US-GAAP/XBRL format.",
                )]

            lines = [
                f"Financial Snapshot: {ticker.upper()}",
                f"Source: SEC EDGAR XBRL (latest filing)",
                "=" * 70,
            ]

            # Quick metrics summary
            qm = data.get("quick_metrics")
            if qm:
                lines.extend(["", "── Key Metrics ──"])
                metric_pairs = [
                    ("Revenue", qm.get("revenue")),
                    ("Net Income", qm.get("net_income")),
                    ("Operating Income", qm.get("operating_income")),
                    ("Total Assets", qm.get("total_assets")),
                    ("Total Liabilities", qm.get("total_liabilities")),
                    ("Stockholders' Equity", qm.get("stockholders_equity")),
                    ("Operating Cash Flow", qm.get("operating_cash_flow")),
                    ("Free Cash Flow", qm.get("free_cash_flow")),
                    ("Capital Expenditures", qm.get("capital_expenditures")),
                ]
                for label, val in metric_pairs:
                    if val is not None:
                        lines.append(f"  {label:<25} {_format_usd(val, 'USD'):>18}")

                # Liquidity & leverage ratios
                cr = qm.get("current_ratio")
                dta = qm.get("debt_to_assets")
                ca = qm.get("current_assets")
                cl = qm.get("current_liabilities")
                sh_b = qm.get("shares_outstanding_basic")
                sh_d = qm.get("shares_outstanding_diluted")

                if any(v is not None for v in [cr, dta, ca, cl]):
                    lines.extend(["", "── Ratios & Shares ──"])
                    if ca is not None:
                        lines.append(f"  {'Current Assets':<25} {_format_usd(ca, 'USD'):>18}")
                    if cl is not None:
                        lines.append(f"  {'Current Liabilities':<25} {_format_usd(cl, 'USD'):>18}")
                    if cr is not None:
                        lines.append(f"  {'Current Ratio':<25} {cr:>18.2f}")
                    if dta is not None:
                        lines.append(f"  {'Debt / Assets':<25} {dta:>18.2%}")
                    if sh_b is not None:
                        lines.append(f"  {'Shares Basic':<25} {_format_usd(sh_b, 'shares'):>18}")
                    if sh_d is not None:
                        lines.append(f"  {'Shares Diluted':<25} {_format_usd(sh_d, 'shares'):>18}")

            # Detailed statements
            for stmt_key, stmt_title in [
                ("income_statement", "INCOME STATEMENT"),
                ("balance_sheet", "BALANCE SHEET"),
                ("cashflow_statement", "CASH FLOW STATEMENT"),
            ]:
                stmt = data.get(stmt_key)
                if not stmt:
                    continue

                periods = stmt.get("periods", [])
                rows = stmt.get("rows", [])

                if not periods or not rows:
                    continue

                lines.extend(["", f"── {stmt_title} ──"])

                # Header row
                header = f"{'Line Item':<45}"
                for p in periods[:3]:  # max 3 periods for readability
                    header += f"{p:>18}"
                lines.append(header)
                lines.append("-" * (45 + 18 * min(len(periods), 3)))

                for row in rows:
                    label = row.get("label", "")
                    if len(label) > 43:
                        label = label[:40] + "..."

                    line = f"{label:<45}"
                    for p in periods[:3]:
                        val = row.get(p)
                        if val is not None:
                            line += f"{_format_usd(float(val), 'USD'):>18}"
                        else:
                            line += f"{'—':>18}"
                    lines.append(line)

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_financial_snapshot error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def get_per_share_fundamentals(
        ticker: str,
        periods: int = 10,
    ) -> List[TextContent]:
        """Get historical per-share fundamentals from SEC XBRL filings.
        Returns annual series of key valuation inputs computed from
        actual reported values — replaces paid data services like SimFin.

        Metrics returned per year:
          - Diluted Shares Outstanding (weighted average, millions)
          - Book Value per Share (Equity / Diluted Shares)
          - Tangible Book Value per Share ((Equity - Goodwill - Intangibles) / Shares)
          - Revenue per Share
          - Operating Cash Flow per Share
          - Diluted EPS (Net Income / Diluted Shares, split-adjusted)
          - Total Revenue (millions)
          - Operating Cash Flow (millions)

        Args:
            ticker: Stock ticker symbol.
            periods: Number of annual periods (default 10, max ~10 years of data).
        """
        try:
            data = edgar.get_per_share_fundamentals(ticker, periods=periods)

            if not data:
                return [TextContent(
                    type="text",
                    text=f"No per-share fundamentals found for {ticker.upper()}. "
                         f"The company may not have usable annual XBRL filings.",
                )]

            rows = data["rows"]
            entity_name = data.get("entity_name", ticker.upper())
            concepts = data.get("concepts_used", {})

            lines = [
                f"Per-Share Fundamentals: {ticker.upper()} — {entity_name}",
                f"Source: SEC EDGAR XBRL (annual filings: 10-K / 20-F / 40-F)",
                "=" * 95,
            ]

            # Show concept fallback notes only when a non-default was used
            fallbacks = {
                k: v for k, v in concepts.items()
                if v and v not in (
                    "WeightedAverageNumberOfDilutedSharesOutstanding",
                    "StockholdersEquity", "Goodwill",
                    "IntangibleAssetsNetExcludingGoodwill", "Revenues",
                    "NetCashProvidedByUsedInOperatingActivities",
                    "NetIncomeLoss",
                )
            }
            if fallbacks:
                notes = ", ".join(f"{k}={v}" for k, v in fallbacks.items())
                lines.append(f"Concept fallbacks: {notes}")
            if concepts.get("shares_note"):
                lines.append(f"Share fallback: {concepts['shares_note']}")

            lines.extend([
                "",
                f"{'Year':<6}"
                f"{'Shares(M)':>11}"
                f"{'BV/Shr':>10}"
                f"{'TBV/Shr':>10}"
                f"{'Rev/Shr':>10}"
                f"{'OCF/Shr':>10}"
                f"{'EPS':>10}"
                f"{'Revenue(M)':>14}"
                f"{'OpCF(M)':>14}",
                "-" * 95,
            ])

            for r in rows:
                def _fmt(val, fmt_str=",.2f"):
                    if val is None:
                        return "—"
                    return f"{val:{fmt_str}}"

                def _fmt_m(val):
                    """Format as millions."""
                    if val is None:
                        return "—"
                    return f"{val / 1_000_000:,.0f}"

                lines.append(
                    f"{r['year']:<6}"
                    f"{_fmt(r.get('diluted_shares_m'), ',.1f'):>11}"
                    f"{_fmt(r.get('book_value_per_share')):>10}"
                    f"{_fmt(r.get('tangible_bv_per_share')):>10}"
                    f"{_fmt(r.get('revenue_per_share')):>10}"
                    f"{_fmt(r.get('opcf_per_share')):>10}"
                    f"{_fmt(r.get('eps_diluted')):>10}"
                    f"{_fmt_m(r.get('total_revenue')):>14}"
                    f"{_fmt_m(r.get('operating_cash_flow')):>14}"
                )

            notes = [
                "",
                "Notes:",
                "  BV/Shr = Stockholders' Equity / Weighted Avg Diluted Shares",
                "  TBV/Shr = (Equity - Goodwill - Intangible Assets) / Diluted Shares",
                "  EPS = Net Income / Diluted Shares (split-adjusted)",
                "  All values from annual filings (10-K / 20-F / 40-F). Shares are weighted avg diluted.",
            ]
            if data.get("split_adjusted"):
                yrs = data.get("split_adjusted_years", [])
                notes.append(f"  Split-adjusted years: {', '.join(str(y) for y in yrs)}")
            lines.extend(notes)

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"get_per_share_fundamentals error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
