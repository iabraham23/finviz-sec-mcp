"""
SEC EDGAR API Client
Free public API — no key required. Standard Rate limit: 10 requests/second.
Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""

import logging
import os
import re
import time
import requests
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional

load_dotenv()

logger = logging.getLogger(__name__)

# Must include contact email per SEC policy
_sec_email = os.getenv("SEC_EMAIL", "ia@cwcgroup.com")
USER_AGENT = f"FinvizSecMCP {_sec_email}"


class EdgarClient:
    """Client for SEC EDGAR public APIs."""

    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index" #not used 
    FILING_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index" #not used 
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._cik_cache: Dict[str, str] = {}
        self._last_request_time = 0.0

    # ── Rate limiting ──────────────────────────────────────────────────
    def _throttle(self):
        """Enforce 10 req/sec rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        self._throttle()
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp

    # ── Ticker → CIK resolution ───────────────────────────────────────
    def get_cik(self, ticker: str) -> Optional[str]:
        """Resolve a ticker symbol to a zero-padded 10-digit CIK."""
        ticker = ticker.upper().strip()
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]

        try:
            data = self._get(self.COMPANY_TICKERS_URL).json()
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                self._cik_cache[t] = cik
                if t == ticker:
                    return cik
        except Exception as e:
            logger.error(f"CIK lookup failed for {ticker}: {e}")
        return None

    # ── Company submissions (filing list) ──────────────────────────────
    def get_filings(
        self,
        ticker: str,
        form_types: Optional[List[str]] = None,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get recent SEC filings for a company.

        Args:
            ticker: Stock ticker symbol.
            form_types: Filter to specific forms (e.g. ["10-K", "10-Q", "8-K"]).
            max_results: Maximum filings to return.
        """
        cik = self.get_cik(ticker)
        if not cik:
            return []

        try:
            url = self.SUBMISSIONS_URL.format(cik=cik)
            data = self._get(url).json()
            recent = data.get("filings", {}).get("recent", {})

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            primary_docs = recent.get("primaryDocument", [])
            descriptions = recent.get("primaryDocDescription", [])

            filings = []
            for i in range(len(forms)):
                if form_types and forms[i] not in form_types:
                    continue

                accession_clean = accessions[i].replace("-", "")
                filing_url = (
                    f"{self.ARCHIVES_URL}/{int(cik)}/{accession_clean}/{primary_docs[i]}"
                )

                filings.append({
                    "form": forms[i],
                    "date": dates[i],
                    "accession": accessions[i],
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": filing_url,
                })

                if len(filings) >= max_results:
                    break

            return filings

        except Exception as e:
            logger.error(f"Failed to get filings for {ticker}: {e}")
            return []

    # ── Company XBRL facts (structured financial data) ─────────────────
    def get_company_facts(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get XBRL financial facts for a company.
        Returns structured data including revenue, net income, EPS, assets, etc.
        """
        cik = self.get_cik(ticker)
        if not cik:
            return None

        try:
            url = self.COMPANY_FACTS_URL.format(cik=cik)
            data = self._get(url).json()
            return data
        except Exception as e:
            logger.error(f"Failed to get company facts for {ticker}: {e}")
            return None

    def get_financial_metric(
        self,
        ticker: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
        periods: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Extract a specific financial metric from XBRL data.

        Args:
            ticker: Stock ticker.
            concept: XBRL concept name (e.g. "Revenues", "NetIncomeLoss",
                     "EarningsPerShareBasic", "Assets", "StockholdersEquity").
            taxonomy: XBRL taxonomy (default "us-gaap").
            unit: Unit filter (e.g. "USD", "USD/shares").
            periods: Number of recent periods to return.
        """
        facts = self.get_company_facts(ticker)
        if not facts:
            return []

        try:
            concept_data = (
                facts.get("facts", {})
                .get(taxonomy, {})
                .get(concept, {})
                .get("units", {})
                .get(unit, [])
            )

            # Filter to annual (10-K) and quarterly (10-Q) filings
            filtered = [
                {
                    "end": entry.get("end"),
                    "val": entry.get("val"),
                    "form": entry.get("form"),
                    "fy": entry.get("fy"),
                    "fp": entry.get("fp"),
                    "filed": entry.get("filed"),
                }
                for entry in concept_data
                if entry.get("form") in ("10-K", "10-Q")
            ]

            # Return most recent periods
            filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
            return filtered[:periods]

        except Exception as e:
            logger.error(f"Failed to extract {concept} for {ticker}: {e}")
            return []

    # ── Filing text retrieval ──────────────────────────────────────────
    def get_filing_text(
        self, ticker: str, form_type: str = "10-K", max_chars: int = 15000
    ) -> Optional[Dict[str, str]]:
        """
        Fetch the most recent filing of a given type and return its text.
        Truncated to max_chars to fit in context windows.
        """
        filings = self.get_filings(ticker, form_types=[form_type], max_results=1)
        if not filings:
            return None

        filing = filings[0]
        try:
            resp = self._get(filing["url"])
            text = resp.text

            # Strip HTML tags for readability
            clean = re.sub(r"<[^>]+>", " ", text)
            clean = re.sub(r"\s+", " ", clean).strip()

            return {
                "form": filing["form"],
                "date": filing["date"],
                "url": filing["url"],
                "text": clean[:max_chars],
                "truncated": len(clean) > max_chars,
            }
        except Exception as e:
            logger.error(f"Failed to fetch filing text for {ticker}: {e}")
            return None
