"""
Stock Screener Tools
Finviz-powered screening with 67+ filters.
"""

import logging
from typing import List
from mcp.types import TextContent

from ..clients.finviz_client import FinvizClient

logger = logging.getLogger(__name__)
client = FinvizClient()


def register_screener_tools(server):
    """Register all screener tools with the MCP server."""

    @server.tool()
    def screen_stocks(
        filters: str,
        table: str = "Valuation",
        order: str = "-marketcap",
        signal: str = "",
        max_results: int = 30,
    ) -> List[TextContent]:
        """Screen stocks using Finviz filter codes. This is the primary tool
        for finding value investments.

        Args:
            filters: Comma-separated Finviz filter codes.
                VALUE INVESTING EXAMPLES:
                  "cap_largeover,fa_pe_u20,fa_roe_o15"
                      → Large cap, P/E < 20, ROE > 15%
                  "fa_pb_u2,fa_curratio_o1.5,fa_debteq_u0.5"
                      → P/B < 2, current ratio > 1.5, debt/equity < 0.5
                  "fa_div_o3,fa_payoutratio_u60,fa_roe_o15"
                      → Dividend > 3%, payout < 60%, ROE > 15%
                  "fa_pfcf_u15,fa_opermargin_o15,fa_epsyoy1_o10"
                      → P/FCF < 15, op margin > 15%, EPS growth > 10%

                USE TOOL: list_filter_options TO SEE ALL FILTERS 
                
                COMMON FILTER PREFIXES:
                  cap_     : Market cap (nano/micro/small/mid/large/mega)
                  fa_pe    : P/E ratio (u = under, o = over)
                  fa_fpe   : Forward P/E
                  fa_peg   : PEG ratio
                  fa_ps    : Price/Sales
                  fa_pb    : Price/Book
                  fa_pc    : Price/Cash
                  fa_pfcf  : Price/Free Cash Flow
                  fa_roe   : Return on equity
                  fa_roa   : Return on assets
                  fa_roi   : Return on investment
                  fa_curratio  : Current ratio
                  fa_quickratio: Quick ratio
                  fa_debteq    : Debt/Equity
                  fa_ltdebteq  : Long-term Debt/Equity
                  fa_grossmargin : Gross margin
                  fa_opermargin  : Operating margin
                  fa_netmargin   : Net profit margin
                  fa_div   : Dividend yield
                  fa_epsyoy5     : EPS growth past 5 years
                  fa_salesqoq    : Sales growth QoQ
                  sec_     : Sector (technology, healthcare, etc.)
                  ind_     : Industry
                  sh_avgvol: Average volume
                  ta_sma200: Price vs 200-day SMA

            table: Data view that controls which columns are returned.
                   Each view returns different metrics per stock:

                   "Overview" — Company, Sector, Industry, Market Cap, P/E,
                       Price, Change, Volume
                   "Valuation" — Market Cap, P/E, Fwd P/E, PEG, P/S, P/B,
                       P/C, P/FCF, EPS This Y, EPS Next Y, EPS Past 5Y,
                       EPS Next 5Y, Sales Past 5Y, Price, Change, Volume
                   "Financial" — Market Cap, Dividend, ROA, ROE, ROI,
                       Curr R (Current Ratio), Quick R, LTDebt/Eq, Debt/Eq,
                       Gross M, Oper M, Profit M, Earnings, Price, Change, Volume
                   "Ownership" — Market Cap, Outstanding, Float, Insider Own,
                       Insider Trans, Inst Own, Inst Trans, Float Short,
                       Short Ratio, Avg Volume, Price, Change, Volume
                   "Performance" — Perf Week, Perf Month, Perf Quart,
                       Perf Half, Perf Year, Perf YTD, Volatility W,
                       Volatility M, Recom, Avg Volume, Rel Volume,
                       Price, Change, Volume
                   "Technical" — Beta, ATR, SMA20, SMA50, SMA200,
                       52W High, 52W Low, RSI, Price, Change, Volume

                   Use "Valuation" for value metrics, "Financial" for margins/ROE.
            order: Sort column. Prefix with '-' for descending.
                   e.g. "-marketcap", "pe", "-dividendyield"
            signal: Optional Finviz signal preset, e.g. "ta_topgainers".
            max_results: Max stocks to return (default 30).

        Returns:
            Formatted screening results with key metrics.
        """
        try:
            filter_list = [f.strip() for f in filters.split(",") if f.strip()]
            results = client.screen(
                filters=filter_list, table=table, order=order, signal=signal
            )

            if not results:
                return [TextContent(
                    type="text",
                    text=f"No stocks found matching filters: {filters}\n\n"
                         f"Tip: Try relaxing some filters. Use list_filter_options "
                         f"to see valid values.",
                )]

            results = results[:max_results]

            lines = [
                f"Screening Results — {len(results)} stocks",
                f"Filters: {filters}",
                f"View: {table} | Sort: {order}"
                + (f" | Signal: {signal}" if signal else ""),
                "=" * 65,
                "",
            ]

            for stock in results:
                ticker = stock.get("Ticker", "?")
                company = stock.get("Company", "?")
                lines.append(f"▸ {ticker} — {company}")

                # Show all available fields from the table view
                detail_parts = []
                for key, val in stock.items():
                    if key not in ("No.", "Ticker", "Company") and val:
                        detail_parts.append(f"{key}: {val}")

                # Format in rows of 3–4 metrics
                for i in range(0, len(detail_parts), 4):
                    chunk = detail_parts[i : i + 4]
                    lines.append(f"  {' | '.join(chunk)}")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]

        except Exception as e:
            logger.error(f"screen_stocks error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.tool()
    def screen_value_stocks(
        min_market_cap: str = "mid",
        max_pe: str = "u25",
        min_roe: str = "o10",
        max_debt_equity: str = "u1",
        additional_filters: str = "",
    ) -> List[TextContent]:
        """Quick value stock screener with sensible defaults.

        Args:
            min_market_cap: Minimum market cap — "small", "mid", "large", "mega".
                Maps to: small=cap_smallover, mid=cap_midover,
                         large=cap_largeover, mega=cap_mega
            max_pe: Max P/E — e.g. "u20" for under 20, "u15" for under 15.
            min_roe: Min ROE — e.g. "o10" for over 10%, "o15" for over 15%.
            max_debt_equity: Max debt/equity — e.g. "u1" for under 1, "u0.5".
            additional_filters: Extra raw filter codes (comma-separated).
                e.g. "fa_div_o2,sec_consumerdefensive"
        """
        cap_map = {
            "small": "cap_smallover",
            "mid": "cap_midover",
            "large": "cap_largeover",
            "mega": "cap_mega",
        }
        cap_filter = cap_map.get(min_market_cap, "cap_midover")

        filters = [
            cap_filter,
            f"fa_pe_{max_pe}",
            f"fa_roe_{min_roe}",
            f"fa_debteq_{max_debt_equity}",
        ]

        if additional_filters:
            filters.extend(
                [f.strip() for f in additional_filters.split(",") if f.strip()]
            )

        filter_str = ",".join(filters)
        results = client.screen(
            filters=filters, table="Valuation", order="-marketcap"
        )

        if not results:
            return [TextContent(
                type="text",
                text=f"No stocks matched the value criteria: {filter_str}\n"
                     f"Try relaxing max_pe or max_debt_equity.",
            )]

        results = results[:30]
        lines = [
            "Value Stock Screen Results",
            f"Criteria: Market Cap ≥ {min_market_cap} | P/E {max_pe} | "
            f"ROE {min_roe} | D/E {max_debt_equity}",
            f"Raw filters: {filter_str}",
            "=" * 65,
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

    @server.tool()
    def screen_from_url(url: str) -> List[TextContent]:
        """Run a Finviz screener from a URL you copied from finviz.com.

        Args:
            url: Full Finviz screener URL, e.g.
                 "https://finviz.com/screener.ashx?v=111&f=cap_largeover,fa_pe_u20"
        """
        try:
            results = client.screen_from_url(url)
            if not results:
                return [TextContent(type="text", text="No results from that URL.")]

            results = results[:40]

            lines = [
                f"URL Screen Results — {len(results)} stocks",
                f"Source: {url}",
                "=" * 65,
                "",
            ]

            for stock in results:
                ticker = stock.get("Ticker", "?")
                company = stock.get("Company", "?")
                lines.append(f"▸ {ticker} — {company}")

                # Show all available fields (same format as screen_stocks)
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

    @server.tool()
    def list_filter_options() -> List[TextContent]:
        """List all available Finviz screener filter categories and their codes.
        Use this to discover valid filter values for screen_stocks.
        """
        try:
            filters_dict = client.get_available_filters()
            if not filters_dict:
                return [TextContent(
                    type="text",
                    text="Could not load filter dictionary. "
                         "The finviz package may need updating.",
                )]

            lines = [
                "Available Finviz Screener Filters",
                "=" * 60,
                "",
            ]
            for category, options in sorted(filters_dict.items()):
                lines.append(f"▸ {category}")
                if isinstance(options, dict):
                    for code, label in list(options.items())[:15]:
                        lines.append(f"    {code} → {label}")
                    if len(options) > 15:
                        lines.append(f"    ... and {len(options) - 15} more")
                lines.append("")

            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]
