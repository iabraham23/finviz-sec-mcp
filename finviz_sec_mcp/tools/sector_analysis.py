"""
Sector & Industry Analysis Tools
Aggregate data from Finviz groups endpoint.
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()


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
