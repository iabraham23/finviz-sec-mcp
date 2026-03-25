"""
Yahoo Finance Client — free historical price data via yfinance.

Provides annual high, low, and average close prices for stock tickers.
No API key required.
"""

import logging
from typing import Any, Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)


class YFinanceClient:
    """Client for historical stock price data via yfinance."""

    def get_annual_price_history(
        self,
        ticker: str,
        years: int = 11,
    ) -> Optional[Dict[str, Any]]:
        """
        Get annual high, low, and average close prices.

        Args:
            ticker: Stock ticker symbol.
            years: Number of years of history (default 11 for 2016-2026 range).

        Returns:
            Dict with ticker, rows (year, high, low, avg_close), or None on failure.
        """
        ticker = ticker.upper().strip()
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=f"{years}y")

            if hist.empty:
                return None

            # Group by calendar year
            hist_year = hist.index.year

            rows: List[Dict[str, Any]] = []
            for year in sorted(hist_year.unique(), reverse=True):
                year_data = hist[hist_year == year]
                rows.append({
                    "year": int(year),
                    "high": round(float(year_data["High"].max()), 2),
                    "low": round(float(year_data["Low"].min()), 2),
                    "avg_close": round(float(year_data["Close"].mean()), 2),
                })

            return {
                "ticker": ticker,
                "periods": len(rows),
                "rows": rows,
            }

        except Exception as e:
            logger.error(f"Failed to get price history for {ticker}: {e}")
            return None
