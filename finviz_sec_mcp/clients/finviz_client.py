"""
Utilizes Finviz Client.
No API key or Elite subscription required.
Data is delayed 15–20 min -- Support for Elite not available yet  
"""

import logging
from typing import Any, Dict, List

import finviz
from finviz.screener import Screener

logger = logging.getLogger(__name__)


class FinvizClient:
    """Thin wrapper around the free finviz package."""

    # ── Single stock data ──────────────────────────────────────────────
    @staticmethod
    def get_stock(ticker: str) -> Dict[str, str]:
        """Get 90+ fundamental data points for a single stock."""
        return finviz.get_stock(ticker.upper().strip())

    @staticmethod
    def get_multiple_stocks(tickers: List[str]) -> List[Dict[str, str]]:
        """Get fundamentals for multiple stocks."""
        results = []
        for t in tickers:
            try:
                data = finviz.get_stock(t.upper().strip())
                data["Ticker"] = t.upper().strip()
                results.append(data)
            except Exception as e:
                logger.warning(f"Failed to fetch {t}: {e}")
                results.append({"Ticker": t.upper(), "error": str(e)})
        return results

    # ── Screener ───────────────────────────────────────────────────────
    @staticmethod
    def screen(
        filters: List[str],
        table: str = "Overview",
        order: str = "",
        signal: str = "",
    ) -> List[Dict[str, str]]:
        """
        Run a Finviz screener with raw filter codes.

        Args:
            filters: List of Finviz filter codes, e.g.
                     ["cap_largeover", "fa_pe_u20", "fa_roe_o15"]
            table: View type — Overview, Valuation, Financial,
                   Ownership, Performance, Technical
            order: Sort column (prefix with '-' for desc), e.g. "-marketcap"
            signal: Optional signal like "ta_topgainers"

        Returns:
            List of stock dictionaries.
        """
        kwargs = {"filters": filters, "table": table}
        if order:
            kwargs["order"] = order
        if signal:
            kwargs["signal"] = signal

        try:
            screener = Screener(**kwargs)
            return list(screener)
        except Exception as e:
            logger.error(f"Screener failed: {e}")
            return []

    @staticmethod
    def screen_from_url(url: str) -> List[Dict[str, str]]:
        """Initialize a screener from a Finviz URL."""
        try:
            screener = Screener.init_from_url(url)
            return list(screener)
        except Exception as e:
            logger.error(f"URL screener failed: {e}")
            return []

    # ── News ───────────────────────────────────────────────────────────
    @staticmethod
    def get_news(ticker: str) -> List[tuple]:
        """Get recent news for a ticker."""
        try:
            return finviz.get_news(ticker.upper().strip())
        except Exception as e:
            logger.error(f"News fetch failed for {ticker}: {e}")
            return []

    # ── Insider activity ───────────────────────────────────────────────
    @staticmethod
    def get_insider(ticker: str) -> List[Dict[str, str]]:
        """Get insider trading activity."""
        try:
            return finviz.get_insider(ticker.upper().strip())
        except Exception as e:
            logger.error(f"Insider data failed for {ticker}: {e}")
            return []

    # ── Analyst targets ────────────────────────────────────────────────
    @staticmethod
    def get_analyst_targets(
        ticker: str, last_ratings: int = 10
    ) -> List[Dict[str, Any]]:
        """Get analyst price targets and ratings."""
        try:
            return finviz.get_analyst_price_targets(
                ticker.upper().strip(), last_ratings=last_ratings
            )
        except Exception as e:
            logger.error(f"Analyst data failed for {ticker}: {e}")
            return []

    # ── Available filters ──────────────────────────────────────────────
    @staticmethod
    def get_available_filters() -> Dict[str, Any]:
        """Return all available Finviz filter options."""
        try:
            return Screener.load_filter_dict()
        except Exception as e:
            logger.error(f"Failed to load filters: {e}")
            return {}
