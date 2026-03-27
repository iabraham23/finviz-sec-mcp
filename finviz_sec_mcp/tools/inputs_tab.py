"""
Inputs-tab extraction tool for the valuation workbook.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ..clients.edgar_client import EdgarClient
from ..clients.finviz_client import FinvizClient
from ..clients.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)
finviz_client = FinvizClient()
edgar_client = EdgarClient()
yf_client = YFinanceClient()


def _parse_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == "-":
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return None


def _parse_suffix_number(raw: Any) -> Optional[float]:
    """Parse values like 3.62B, 470.89M, 10.73B into raw numbers."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == "-":
        return None

    match = re.match(r"^(-?\d+(?:\.\d+)?)([KMBT])?$", text.replace(",", ""))
    if not match:
        return None

    value = float(match.group(1))
    suffix = match.group(2)
    multiplier = {
        None: 1.0,
        "K": 1_000.0,
        "M": 1_000_000.0,
        "B": 1_000_000_000.0,
        "T": 1_000_000_000_000.0,
    }[suffix]
    return value * multiplier


def _parse_price_field(raw: Any) -> Optional[float]:
    """Parse values like '258.60 -22.92%' by taking the leading price."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == "-":
        return None
    match = re.match(r"^(-?\d+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def _round_or_none(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _normalize_market_cap_millions(raw: Any) -> Optional[float]:
    value = _parse_suffix_number(raw)
    if value is None:
        return None
    return value / 1_000_000


def _normalize_shares_millions(raw: Any) -> Optional[float]:
    value = _parse_suffix_number(raw)
    if value is None:
        return None
    return value / 1_000_000


def _get_industry_aggregate(industry_name: str) -> Optional[Dict[str, str]]:
    rows = finviz_client.get_groups(group="industry", view="overview", order="name")
    for row in rows:
        if row.get("Name", "").lower() == industry_name.lower():
            return row
    return None


def _format_num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _format_intish(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _build_payload(
    ticker: str,
    fundamentals: Dict[str, Any],
    industry_row: Optional[Dict[str, str]],
    price_history: Optional[Dict[str, Any]],
    per_share: Optional[Dict[str, Any]],
    ttm_eps: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    industry_name = fundamentals.get("Industry", "")

    annual_price_history: Dict[str, Dict[str, Optional[float]]] = {}
    for row in (price_history or {}).get("rows", []):
        annual_price_history[str(row["year"])] = {
            "high": _round_or_none(row.get("high")),
            "low": _round_or_none(row.get("low")),
            "avg_close": _round_or_none(row.get("avg_close")),
        }

    historical_fundamentals: Dict[str, Dict[str, Optional[float]]] = {}
    for row in (per_share or {}).get("rows", []):
        historical_fundamentals[str(row["year"])] = {
            "shares_out_millions": _round_or_none(row.get("diluted_shares_m"), 1),
            "book_value_per_share": _round_or_none(row.get("book_value_per_share")),
            "tbv_per_share": _round_or_none(row.get("tangible_bv_per_share")),
            "revenue_per_share": _round_or_none(row.get("revenue_per_share")),
            "op_cf_per_share": _round_or_none(row.get("opcf_per_share")),
            "annual_eps_diluted": _round_or_none(row.get("eps_diluted")),
            "total_revenue_millions": _round_or_none(
                None if row.get("total_revenue") is None else row.get("total_revenue") / 1_000_000,
                0,
            ),
            "op_cash_flow_millions": _round_or_none(
                None if row.get("operating_cash_flow") is None else row.get("operating_cash_flow") / 1_000_000,
                0,
            ),
        }

    payload = {
        "ticker": ticker.upper(),
        "company_identification": {
            "ticker": ticker.upper(),
            "company_name": fundamentals.get("Company"),
            "industry": industry_name or None,
            "sector": fundamentals.get("Sector") or None,
            "current_price": _round_or_none(_parse_float(fundamentals.get("Price"))),
            "shares_outstanding_millions": _round_or_none(
                _normalize_shares_millions(fundamentals.get("Shs Outstand")), 2
            ),
            "market_cap_millions": _round_or_none(
                _normalize_market_cap_millions(fundamentals.get("Market Cap")), 0
            ),
            "avg_daily_volume_3m": _round_or_none(
                _parse_suffix_number(fundamentals.get("Avg Volume")), 0
            ),
            "high_52_week": _round_or_none(_parse_price_field(fundamentals.get("52W High"))),
            "analyst_price_estimate_1y": _round_or_none(
                _parse_float(fundamentals.get("Target Price"))
            ),
            "date_of_analysis": None,
            "date_of_valuation": None,
            "model_year": None,
        },
        "earnings_and_growth": {
            "current_eps": _round_or_none(_parse_float(fundamentals.get("EPS (ttm)"))),
            "forward_eps_next_year": _round_or_none(_parse_float(fundamentals.get("EPS next Y"))),
            "eps_growth_5y": _round_or_none(_parse_float(fundamentals.get("EPS next 5Y"))),
            "company_peg": _round_or_none(_parse_float(fundamentals.get("PEG"))),
            "industry_peg": _round_or_none(
                _parse_float(industry_row.get("PEG")) if industry_row else None
            ),
            "forward_pe_consensus": _round_or_none(_parse_float(fundamentals.get("Forward P/E"))),
            "dcf_value_with_risk": None,
            "dcf_value_without_risk": None,
            "cwc_analyst_price_target": None,
        },
        "annual_price_history": annual_price_history,
        "historical_fundamentals": historical_fundamentals,
        "ltm_metrics": {
            "ltm_eps_diluted": _round_or_none(
                None if not ttm_eps else ttm_eps.get("ttm_val")
            )
        },
        "manual_fields": {
            "section_3_weightings": None,
            "dcf_value_with_risk": None,
            "dcf_value_without_risk": None,
            "cwc_analyst_price_target": None,
            "date_of_analysis": None,
            "date_of_valuation": None,
            "model_year": None,
        },
        "sources": {
            "company_identification": "get_stock_fundamentals",
            "earnings_and_growth": ["get_stock_fundamentals", "compare_industries"],
            "annual_price_history": "get_annual_price_history",
            "historical_fundamentals": "get_per_share_fundamentals",
            "ltm_metrics": "get_financial_ttm",
        },
    }
    return payload


def _format_report(payload: Dict[str, Any]) -> str:
    ident = payload["company_identification"]
    growth = payload["earnings_and_growth"]
    price_history = payload["annual_price_history"]
    fundamentals = payload["historical_fundamentals"]
    ltm = payload["ltm_metrics"]

    lines = [
        f"Inputs Tab Data: {payload['ticker']}",
        "=" * 80,
        "",
        "Section 1 — Company Identification",
        f"  Company: {ident['company_name'] or '—'}",
        f"  Industry: {ident['industry'] or '—'} | Sector: {ident['sector'] or '—'}",
        f"  Current Price: ${_format_num(ident['current_price'])}",
        f"  Shares Outstanding (M): {_format_num(ident['shares_outstanding_millions'])}",
        f"  Market Cap ($M): {_format_intish(ident['market_cap_millions'])}",
        f"  Avg Daily Volume (3M): {_format_intish(ident['avg_daily_volume_3m'])}",
        f"  52-Week High: ${_format_num(ident['high_52_week'])}",
        f"  1Y Analyst Price Estimate: ${_format_num(ident['analyst_price_estimate_1y'])}",
        "",
        "Section 2 — Earnings & Growth Assumptions",
        f"  Current EPS (EPS ttm): {_format_num(growth['current_eps'])}",
        f"  Forward EPS (EPS next Y): {_format_num(growth['forward_eps_next_year'])}",
        f"  5Y EPS Growth: {_format_num(growth['eps_growth_5y'])}",
        f"  Company PEG: {_format_num(growth['company_peg'])}",
        f"  Industry PEG: {_format_num(growth['industry_peg'])}",
        f"  Forward P/E: {_format_num(growth['forward_pe_consensus'])}",
        "",
        "Section 4 — Historical Annual Price Data",
        "  Year     High       Low      Avg",
        "  --------------------------------",
    ]

    for year in sorted(price_history.keys()):
        row = price_history[year]
        lines.append(
            f"  {year:<6} ${_format_num(row.get('high')):>8} ${_format_num(row.get('low')):>8} ${_format_num(row.get('avg_close')):>8}"
        )

    lines.extend([
        "",
        "Section 5 — Historical Fundamentals Per Share",
        "  Year    Sh(M)    BV/Shr   TBV/Shr   Rev/Shr   OpCF/Shr    EPS    Rev(M)  OpCF(M)",
        "  -------------------------------------------------------------------------------",
    ])

    for year in sorted(fundamentals.keys()):
        row = fundamentals[year]
        lines.append(
            f"  {year:<6}"
            f"{_format_num(row.get('shares_out_millions'), 1):>8} "
            f"{_format_num(row.get('book_value_per_share')):>8} "
            f"{_format_num(row.get('tbv_per_share')):>9} "
            f"{_format_num(row.get('revenue_per_share')):>9} "
            f"{_format_num(row.get('op_cf_per_share')):>10} "
            f"{_format_num(row.get('annual_eps_diluted')):>7} "
            f"{_format_intish(row.get('total_revenue_millions')):>8} "
            f"{_format_intish(row.get('op_cash_flow_millions')):>8}"
        )

    lines.extend([
        "",
        f"LTM EPS Diluted: {_format_num(ltm.get('ltm_eps_diluted'))}",
        "",
        "Manual / Unresolved Fields",
        "  Date of Analysis, Date of Valuation, Model Year, DCF values, CWC analyst price target, and Section 3 valuation weightings remain manual.",
        "",
        "JSON Payload",
        "```json",
        json.dumps(payload, indent=2, sort_keys=True),
        "```",
    ])

    return "\n".join(lines)


def register_inputs_tab_tools(server) -> None:
    """Register tools for valuation-input extraction."""

    @server.tool()
    def get_inputs_tab_data(
        ticker: str,
        price_years: int = 11,
        fundamentals_years: int = 10,
        peg_basis: str = "industry",
    ) -> List[TextContent]:
        """Get a structured extraction package for the valuation workbook INPUTS tab.

        This tool consolidates the key MCP data needed for the workbook into
        one response, covering:
        - current company snapshot fields
        - current EPS / forward EPS / PEG / forward PE
        - historical annual price data
        - historical per-share fundamentals
        - true TTM diluted EPS

        Conventions:
        - Current EPS uses Finviz `EPS (ttm)`
        - Forward EPS uses Finviz `EPS next Y`
        - PEG basis defaults to industry
        - LTM EPS Diluted uses SEC TTM diluted EPS

        Args:
            ticker: Stock ticker symbol.
            price_years: Number of years for annual price history.
            fundamentals_years: Number of annual periods for per-share fundamentals.
            peg_basis: Currently supports "industry" only.
        """
        try:
            ticker = ticker.upper().strip()
            if peg_basis.lower() != "industry":
                logger.info(
                    f"{ticker}: unsupported peg_basis={peg_basis}; defaulting to industry"
                )

            fundamentals = finviz_client.get_stock(ticker)
            if not fundamentals:
                return [TextContent(type="text", text=f"No current snapshot data found for {ticker}.")]

            industry_row = _get_industry_aggregate(fundamentals.get("Industry", ""))
            price_history = yf_client.get_annual_price_history(ticker, years=price_years)
            per_share = edgar_client.get_per_share_fundamentals(ticker, periods=fundamentals_years)
            ttm_eps = edgar_client.get_financial_ttm(
                ticker,
                concept="EarningsPerShareDiluted",
                unit="USD/shares",
            )

            payload = _build_payload(
                ticker=ticker,
                fundamentals=fundamentals,
                industry_row=industry_row,
                price_history=price_history,
                per_share=per_share,
                ttm_eps=ttm_eps,
            )
            report = _format_report(payload)
            return [TextContent(type="text", text=report)]

        except Exception as e:
            logger.error(f"get_inputs_tab_data error: {e}")
            return [TextContent(type="text", text=f"Error: {e}")]
