"""
Analysis universe monitor — always scan YOUR book, not random market gainers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import yfinance as yf
from mcp.types import TextContent

logger = logging.getLogger(__name__)

WATCHLIST_DIR = Path(__file__).resolve().parents[2] / "watchlists"
UNIVERSE_FILE = WATCHLIST_DIR / "analysis_universe.txt"


def _load_universe() -> list[str]:
    if not UNIVERSE_FILE.exists():
        return []
    out: list[str] = []
    for line in UNIVERSE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.upper())
    return sorted(set(out))


def register_universe_tools(server):
    """Register tools that operate on analysis_universe.txt only."""

    @server.tool()
    def get_analysis_universe() -> List[TextContent]:
        """List tickers in the canonical analysis book (themes + Asia ADRs)."""
        tickers = _load_universe()
        lines = [
            f"Analysis universe — {len(tickers)} tickers",
            f"File: watchlists/analysis_universe.txt",
            "",
            ", ".join(tickers),
        ]
        return [TextContent(type="text", text="\n".join(lines))]

    @server.tool()
    def scan_analysis_universe(
        min_abs_change_pct: float = 1.0,
        top_n: int = 25,
    ) -> List[TextContent]:
        """Snapshot price/% change/volume for every ticker in analysis_universe.txt.

        This is the primary feed — scan YOUR book first, not marketwide gainers.

        Args:
            min_abs_change_pct: Only show movers with |change| >= this % (default 1.0).
            top_n: Max rows to return, sorted by |change| desc (default 25).
        """
        tickers = _load_universe()
        if not tickers:
            return [
                TextContent(
                    type="text",
                    text="analysis_universe.txt is empty or missing.",
                )
            ]

        try:
            # Bulk download — one yfinance call for the whole book
            raw = yf.download(
                tickers,
                period="5d",
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as e:
            logger.error("scan_analysis_universe download: %s", e)
            return [TextContent(type="text", text=f"Error fetching universe: {e}")]

        rows: list[dict] = []
        for sym in tickers:
            try:
                if len(tickers) == 1:
                    frame = raw
                else:
                    if sym not in raw.columns.get_level_values(0):
                        continue
                    frame = raw[sym]
                frame = frame.dropna(how="all")
                if frame.empty or len(frame) < 2:
                    continue
                last = float(frame["Close"].iloc[-1])
                prev = float(frame["Close"].iloc[-2])
                chg_pct = ((last - prev) / prev) * 100 if prev else 0.0
                vol = int(frame["Volume"].iloc[-1]) if "Volume" in frame else 0
                if abs(chg_pct) < min_abs_change_pct:
                    continue
                rows.append(
                    {
                        "ticker": sym,
                        "price": last,
                        "chg_pct": chg_pct,
                        "volume": vol,
                    }
                )
            except Exception:
                continue

        rows.sort(key=lambda r: abs(r["chg_pct"]), reverse=True)
        shown = rows[:top_n]

        lines = [
            f"Analysis universe scan — {len(tickers)} tickers in book",
            f"Movers |change| >= {min_abs_change_pct}%: {len(rows)}",
            "",
            f"{'Ticker':<6} {'Price':>9} {'Chg%':>8} {'Volume':>14}",
            "-" * 42,
        ]
        for r in shown:
            lines.append(
                f"{r['ticker']:<6} {r['price']:>9.2f} {r['chg_pct']:>+7.2f}% "
                f"{r['volume']:>14,}"
            )
        if not shown:
            lines.append("  (no movers above threshold — book is quiet)")
        lines.extend(
            [
                "",
                "Source: yfinance daily bars (last vs prior close).",
                "Use get_stock_news / screen_asia_social_chatter on names above.",
            ]
        )
        return [TextContent(type="text", text="\n".join(lines))]
