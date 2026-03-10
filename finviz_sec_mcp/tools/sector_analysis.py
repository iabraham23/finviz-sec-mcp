"""
Sector & Industry Analysis Tools
Aggregate data from Finviz groups endpoint.
"""

import logging
import re
from typing import List, Optional
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()

# ── Field mapping: industry aggregate column → fundamentals key ──────
# Some fields need light parsing (e.g. "6.89% 17.91%" → take second value for 5Y)
_FIELD_MAP = {
    # Overview view
    "P/E":         "P/E",
    "Fwd P/E":     "Forward P/E",
    "PEG":         "PEG",
    "Dividend":    "Dividend TTM",      # "1.04 (0.40%)" → extract pct
    "LTDebt/Eq":   "LT Debt/Eq",
    "Debt/Eq":     "Debt/Eq",
    "Float Short": "Short Float",
    "Recom":       "Recom",
    # Valuation view (adds these)
    "P/S":         "P/S",
    "P/B":         "P/B",
    "P/C":         "P/C",
    "P/FCF":       "P/FCF",
    "EPS past 5Y": "EPS past 3/5Y",    # "6.89% 17.91%" → second value (5Y)
    "EPS next 5Y": "EPS next 5Y",
    "Sales past 5Y": "Sales past 3/5Y",  # same pattern
    # Performance view
    "Perf Week":   "Perf Week",
    "Perf Month":  "Perf Month",
    "Perf Quart":  "Perf Quarter",
    "Perf Half":   "Perf Half Y",
    "Perf Year":   "Perf Year",
    "Perf YTD":    "Perf YTD",
}

# Columns to skip in comparison (not meaningful for relative analysis)
_SKIP_COLS = {"No.", "Name", "Stocks", "Market Cap", "Change", "Volume",
              "Avg Volume", "Rel Volume"}


def _parse_numeric(raw: str) -> Optional[float]:
    """Extract a numeric value from a Finviz string like '32.88', '0.40%', '-5.81%'."""
    if not raw or raw == "-":
        return None
    # Strip % sign for comparison
    cleaned = raw.replace("%", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _get_stock_value(fundamentals: dict, fund_key: str) -> Optional[float]:
    """Extract a comparable numeric value from fundamentals dict."""
    raw = fundamentals.get(fund_key, "")
    if not raw or raw == "-":
        return None

    # Handle "3/5Y" fields like "6.89% 17.91%" → take second value (5Y)
    if "3/5Y" in fund_key:
        parts = raw.replace("%", "").split()
        if len(parts) >= 2:
            try:
                return float(parts[1])
            except ValueError:
                return None

    # Handle dividend TTM like "1.04 (0.40%)" → extract percentage
    if fund_key == "Dividend TTM":
        m = re.search(r'\(([\d.]+)%\)', raw)
        if m:
            return float(m.group(1))
        return None

    return _parse_numeric(raw)


def _format_group_table(rows: List[dict], title: str, view: str) -> str:
    """Format group data into readable output."""
    if not rows:
        return f"{title}\n{'=' * 60}\n\nNo data returned."

    lines = [title, "=" * 60, ""]

    for row in rows:
        name = row.get("Name", "?")
        no = row.get("No.", "")

        # Skip the row number, show name as header
        lines.append(f"▸ {name}")

        detail_parts = []
        for key, val in row.items():
            if key not in ("No.", "Name") and val:
                detail_parts.append(f"{key}: {val}")

        for i in range(0, len(detail_parts), 4):
            chunk = detail_parts[i : i + 4]
            lines.append(f"  {' | '.join(chunk)}")
        lines.append("")

    return "\n".join(lines)


def register_sector_tools(server):
    """Register sector analysis tools."""

    @server.tool()
    def compare_sectors(
        view: str = "overview",
        order: str = "name",
    ) -> List[TextContent]:
        """Compare all market sectors with aggregate metrics from Finviz.
        Returns sector-level aggregates (median P/E, total market cap, etc.)
        for all 11 sectors in a single view.

        Args:
            view: Data view to return. Options:
                "overview"    — Stocks, Market Cap, Dividend, P/E, Fwd P/E,
                                PEG, LTDebt/Eq, Debt/Eq, Float Short, Recom,
                                Change, Volume
                "valuation"   — Market Cap, P/E, Fwd P/E, PEG, P/S, P/B,
                                P/C, P/FCF, EPS past 5Y, EPS next 5Y,
                                Sales past 5Y, Change, Volume
                "performance" — Perf Week, Perf Month, Perf Quart, Perf Half,
                                Perf Year, Perf YTD, Avg Volume, Rel Volume,
                                Change, Volume
            order: Sort column — e.g. "name", "marketcap", "pe",
                   "change", "volume", "dividendyield".
        """
        try:
            rows = client.get_groups(
                group="sector", view=view, order=order
            )
            title = f"Sector Comparison — {view.title()} View"
            text = _format_group_table(rows, title, view)
            return [TextContent(type="text", text=text)]

        except Exception as e:
            logger.error(f"compare_sectors error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def compare_industries(
        view: str = "overview",
        order: str = "name",
    ) -> List[TextContent]:
        """Compare all industries with aggregate metrics from Finviz.
        Returns industry-level aggregates for all ~144 industries.

        Args:
            view: Data view — "overview", "valuation", or "performance".
                See compare_sectors for column details per view.
            order: Sort column — e.g. "name", "marketcap", "pe",
                   "change", "volume", "dividendyield".
        """
        try:
            rows = client.get_groups(
                group="industry", view=view, order=order
            )
            title = f"Industry Comparison — {view.title()} View"
            text = _format_group_table(rows, title, view)
            return [TextContent(type="text", text=text)]

        except Exception as e:
            logger.error(f"compare_industries error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def stock_vs_industry(
        ticker: str,
    ) -> List[TextContent]:
        """Get a stock's valuation and fundamentals relative to its industry.
        Compares the stock's metrics against industry aggregates across
        overview (P/E, PEG, Debt, Dividend), valuation (P/S, P/B, P/FCF,
        EPS growth), and performance (weekly through YTD returns).

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL", "BRK-B").
        """
        try:
            # 1. Get stock fundamentals (includes Industry field)
            fundamentals = client.get_stock(ticker)
            industry_name = fundamentals.get("Industry", "")
            company = fundamentals.get("Company", ticker.upper())

            if not industry_name:
                return [TextContent(
                    type="text",
                    text=f"Could not determine industry for {ticker.upper()}.",
                )]

            # 2. Fetch industry aggregates for all 3 views
            lines = [
                f"{ticker.upper()} ({company}) vs. {industry_name} Industry",
                "=" * 65,
                "",
            ]

            for view in ["overview", "valuation", "performance"]:
                rows = client.get_groups(
                    group="industry", view=view, order="name"
                )

                # Find matching industry row
                match = None
                for row in rows:
                    if row.get("Name", "").lower() == industry_name.lower():
                        match = row
                        break

                if not match:
                    lines.append(f"▸ {view.title()} View")
                    lines.append(f"  Industry '{industry_name}' not found in aggregates")
                    lines.append("")
                    continue

                lines.append(f"▸ {view.title()} View")
                lines.append(f"  {'Metric':<18} {'Stock':>10} {'Industry':>10} {'Delta':>10}")
                lines.append(f"  {'-'*18} {'-'*10} {'-'*10} {'-'*10}")

                for col, val in match.items():
                    if col in _SKIP_COLS:
                        continue

                    # Get industry value
                    ind_val = _parse_numeric(val)
                    if ind_val is None:
                        continue

                    # Get corresponding stock value
                    fund_key = _FIELD_MAP.get(col)
                    if not fund_key:
                        continue

                    stock_val = _get_stock_value(fundamentals, fund_key)
                    if stock_val is None:
                        lines.append(f"  {col:<18} {'N/A':>10} {val:>10} {'':>10}")
                        continue

                    # Calculate delta
                    is_pct = "%" in val or "Perf" in col
                    if is_pct:
                        delta = stock_val - ind_val
                        delta_str = f"{delta:+.2f}pp"
                        stock_str = f"{stock_val:.2f}%"
                    elif ind_val != 0:
                        delta_pct = ((stock_val - ind_val) / abs(ind_val)) * 100
                        delta_str = f"{delta_pct:+.1f}%"
                        stock_str = f"{stock_val:.2f}"
                    else:
                        delta_str = "N/A"
                        stock_str = f"{stock_val:.2f}"

                    lines.append(
                        f"  {col:<18} {stock_str:>10} {val:>10} {delta_str:>10}"
                    )

                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"stock_vs_industry error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def screen_industry(
        industry: str,
        table: str = "Valuation",
        additional_filters: str = "",
        max_results: int = 20,
    ) -> List[TextContent]:
        """Screen stocks within a specific industry.

        Args:
            industry: Finviz industry code, e.g.:
                "banksregional", "biotechnology", "semiconductors",
                "softwareinfrastructure", "oilgasep", "drugmanufacturers",
                "insurancelife", "medicaldevices", "reitsdiversified",
                "aerospacedefense", "automanufacturers"

                Use list_filter_options to see all available industries.
            table: Metric view — "Valuation", "Financial", etc.
            additional_filters: Extra Finviz filter codes (comma-separated).
            max_results: Max stocks to return.
        """
        try:
            filters = [f"ind_{industry}"]
            if additional_filters:
                filters.extend(
                    [f.strip() for f in additional_filters.split(",") if f.strip()]
                )

            results = client.screen(
                filters=filters, table=table, order="-marketcap"
            )

            if not results:
                return [TextContent(
                    type="text",
                    text=f"No stocks found in industry '{industry}'. "
                         f"Use list_filter_options to verify the code.",
                )]

            results = results[:max_results]

            lines = [
                f"Industry Screen: {industry} — {len(results)} stocks",
                f"View: {table}",
                "=" * 60,
                "",
            ]

            for stock in results:
                ticker = stock.get("Ticker", "?")
                company = stock.get("Company", "?")
                lines.append(f"▸ {ticker} — {company}")

                detail_parts = []
                for key, val in stock.items():
                    if key not in ("No.", "Ticker", "Company") and val:
                        detail_parts.append(f"{key}: {val}")
                for i in range(0, len(detail_parts), 4):
                    chunk = detail_parts[i : i + 4]
                    lines.append(f"  {' | '.join(chunk)}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]
