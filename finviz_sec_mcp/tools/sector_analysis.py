"""
Sector & Industry Analysis Tools
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()

SECTORS = [
    ("sec_technology", "Technology"),
    ("sec_healthcare", "Healthcare"),
    ("sec_financial", "Financial"),
    ("sec_consumerdefensive", "Consumer Defensive"),
    ("sec_consumercyclical", "Consumer Cyclical"),
    ("sec_industrials", "Industrials"),
    ("sec_energy", "Energy"),
    ("sec_utilities", "Utilities"),
    ("sec_realestate", "Real Estate"),
    ("sec_basicmaterials", "Basic Materials"),
    ("sec_communicationservices", "Communication Services"),
]


def register_sector_tools(server):
    """Register sector analysis tools."""

    @server.tool()
    def compare_sectors(
        table: str = "Valuation",
        sort_by: str = "-marketcap",
    ) -> List[TextContent]:
        """Compare all market sectors by key metrics.
        Screens one representative sample per sector.

        Args:
            table: Metric view — "Valuation", "Financial", "Performance",
                   "Overview", "Ownership", "Technical".
            sort_by: Sort order for stocks within each sector. Default "-marketcap".
        """
        try:
            lines = [
                "Sector Comparison (top stocks per sector)",
                f"View: {table}",
                "=" * 65,
                "",
            ]

            for filter_code, sector_name in SECTORS:
                results = client.screen(
                    filters=[filter_code, "cap_largeover"],
                    table=table,
                    order=sort_by,
                )

                if not results:
                    lines.append(f"▸ {sector_name}: No large-cap results")
                    lines.append("")
                    continue

                # Show top 3 per sector
                lines.append(f"▸ {sector_name} ({len(results)} large-cap stocks)")
                for stock in results[:3]:
                    ticker = stock.get("Ticker", "?")
                    company = stock.get("Company", "?")
                    detail_parts = []
                    for key, val in stock.items():
                        if key not in ("No.", "Ticker", "Company") and val:
                            detail_parts.append(f"{key}: {val}")
                    detail_str = " | ".join(detail_parts[:5])
                    lines.append(f"  {ticker} ({company}): {detail_str}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"compare_sectors error: {e}")
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
