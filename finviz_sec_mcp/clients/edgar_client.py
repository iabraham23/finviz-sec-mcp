"""
SEC EDGAR API Client
Free public API — no key required. Standard Rate limit: 10 requests/second.
Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""

import logging
import os
import re
import threading
import time
import requests
from bs4 import BeautifulSoup
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
    COMPANY_CONCEPT_URL = (
        "https://data.sec.gov/api/xbrl/companyconcept"
        "/CIK{cik}/{taxonomy}/{concept}.json"
    )
    XBRL_FRAMES_URL = (
        "https://data.sec.gov/api/xbrl/frames"
        "/{taxonomy}/{concept}/{unit}/{period}.json"
    )
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

    # Balance sheet concepts are instantaneous (point-in-time) values.
    # Income/cash-flow concepts are duration-based.
    # This matters for the frames endpoint period format.
    INSTANTANEOUS_CONCEPTS = {
        "Assets", "Liabilities", "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments", "Cash",
        "LongTermDebt", "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "CommonStockSharesOutstanding",
    }

    # ── XBRL concept fallback chains ─────────────────────────────────
    # After ASC 606 (2018+), many companies switched revenue tags.
    # When the primary concept doesn't match, try alternatives in order.
    CONCEPT_ALIASES: Dict[str, List[str]] = {
        "Revenues": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
        ],
        "NetIncomeLoss": [
            "NetIncomeLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "ProfitLoss",
        ],
        "OperatingIncomeLoss": [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ],
        "GrossProfit": [
            "GrossProfit",
        ],
        "SellingGeneralAndAdministrativeExpense": [
            "SellingGeneralAndAdministrativeExpense",
            "GeneralAndAdministrativeExpense",
            "SellingAndMarketingExpense",
            "SellingExpense",
        ],
        "ResearchAndDevelopmentExpense": [
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        ],
        "InterestExpense": [
            "InterestExpense",
            "InterestExpenseDebt",
            "InterestAndDebtExpense",
            "InterestCostsIncurred",
        ],
        "IncomeTaxExpenseBenefit": [
            "IncomeTaxExpenseBenefit",
            "IncomeTaxesPaidNet",
        ],
        "EarningsPerShareBasic": [
            "EarningsPerShareBasic",
        ],
        "EarningsPerShareDiluted": [
            "EarningsPerShareDiluted",
        ],
        "LongTermDebt": [
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "LongTermDebtAndCapitalLeaseObligations",
        ],
        "CashAndCashEquivalentsAtCarryingValue": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
            "Cash",
        ],
        "StockholdersEquity": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
        # Cash flow concepts (duration-based, like income)
        "NetCashProvidedByUsedInOperatingActivities": [
            "NetCashProvidedByOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivities",
        ],
        "NetCashProvidedByUsedInFinancingActivities": [
            "NetCashProvidedByUsedInFinancingActivities",
            "NetCashProvidedByFinancingActivities",
        ],
        "NetCashProvidedByUsedInInvestingActivities": [
            "NetCashProvidedByUsedInInvestingActivities",
            "NetCashProvidedByInvestingActivities",
        ],
        "PaymentsOfDividends": [
            "PaymentsOfDividends",
            "PaymentsOfDividendsCommonStock",
            "DividendsCommonStockCash",
            "PaymentsOfOrdinaryDividends",
        ],
        "DepreciationDepletionAndAmortization": [
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ],
        "CapitalExpenditure": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "CapitalExpenditureDiscontinuedOperations",
        ],
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._cik_cache: Dict[str, str] = {}
        self._cik_cache_populated = False
        self._last_request_time = 0.0
        self._throttle_lock = threading.Lock()

    # ── Rate limiting ──────────────────────────────────────────────────
    def _throttle(self):
        """Enforce 10 req/sec rate limit (thread-safe)."""
        with self._throttle_lock:
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
    def _populate_cik_cache(self) -> None:
        """Download the full SEC ticker→CIK map and cache all ~10K entries.
        Only called once (or after a cache-miss retry)."""
        try:
            data = self._get(self.COMPANY_TICKERS_URL).json()
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                self._cik_cache[t] = cik
            self._cik_cache_populated = True
        except Exception as e:
            logger.error(f"CIK cache population failed: {e}")

    def get_cik(self, ticker: str) -> Optional[str]:
        """Resolve a ticker symbol to a zero-padded 10-digit CIK."""
        ticker = ticker.upper().strip()

        # Fast path: already cached
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]

        # First call: populate the entire cache from SEC
        if not self._cik_cache_populated:
            self._populate_cik_cache()
            if ticker in self._cik_cache:
                return self._cik_cache[ticker]

        # Still not found — try one fresh download in case it's newly listed
        if self._cik_cache_populated:
            logger.info(f"CIK miss for {ticker}, retrying with fresh download")
            self._cik_cache_populated = False
            self._populate_cik_cache()
            if ticker in self._cik_cache:
                return self._cik_cache[ticker]

        logger.warning(f"Ticker {ticker} not found in SEC company tickers")
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

    # ── Single-concept lookup (lightweight) ─────────────────────────
    def _get_company_concept(
        self,
        cik: str,
        concept: str,
        taxonomy: str = "us-gaap",
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single XBRL concept for a company via the company-concept
        endpoint.  Much lighter than downloading the full companyfacts blob.
        Returns the raw JSON or None on 404 / error.
        """
        url = self.COMPANY_CONCEPT_URL.format(
            cik=cik, taxonomy=taxonomy, concept=concept,
        )
        try:
            return self._get(url).json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None  # concept doesn't exist for this company
            logger.error(f"Company-concept request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Company-concept request failed: {e}")
            return None

    @staticmethod
    def _deduplicate_entries(
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate XBRL fact entries that share the same period end date.
        A 10-K often restates prior-year figures for comparison, producing
        duplicate 'end' dates.  We keep the most recently *filed* entry
        for each unique (end, form) pair.
        """
        best: Dict[str, Dict[str, Any]] = {}
        for e in entries:
            key = (e.get("end", ""), e.get("form", ""))
            existing = best.get(key)
            if existing is None or e.get("filed", "") > existing.get("filed", ""):
                best[key] = e
        return list(best.values())

    def get_financial_metric(
        self,
        ticker: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
        periods: int = 8,
        form_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract a specific financial metric from XBRL data.
        Uses the lightweight company-concept endpoint with fallback chains
        for concepts that have multiple XBRL tag variants.
        Deduplicates restated figures so each period appears only once.

        Args:
            ticker: Stock ticker.
            concept: XBRL concept name (e.g. "Revenues", "NetIncomeLoss",
                     "EarningsPerShareBasic", "Assets", "StockholdersEquity").
            taxonomy: XBRL taxonomy (default "us-gaap").
            unit: Unit filter (e.g. "USD", "USD/shares").
            periods: Number of recent periods to return.
            form_types: Restrict to specific form types, e.g. ["10-K"] for
                        annual-only or ["10-Q"] for quarterly-only.
                        Defaults to both 10-K and 10-Q.

        Returns:
            List of dicts with keys: end, val, form, fy, fp, filed, concept_used.
        """
        cik = self.get_cik(ticker)
        if not cik:
            return []

        allowed_forms = set(form_types) if form_types else {"10-K", "10-Q"}

        # Derive fiscal-period filter from form_types.
        # 10-K filings contain BOTH the annual total (fp="FY") AND quarterly
        # sub-periods (fp="Q1"/"Q2"/"Q3") for comparison.  Without fp filtering,
        # "annual" requests return quarterly figures mixed into the series.
        if form_types and set(form_types) == {"10-K"}:
            allowed_fp: Optional[set] = {"FY"}
        elif form_types and set(form_types) == {"10-Q"}:
            allowed_fp = {"Q1", "Q2", "Q3", "Q4"}
        else:
            allowed_fp = None  # no fp restriction when mixing form types

        # Build the list of concept names to try
        concepts_to_try = self.CONCEPT_ALIASES.get(concept, [concept])
        if concept not in self.CONCEPT_ALIASES:
            concepts_to_try = [concept]

        for candidate in concepts_to_try:
            try:
                data = self._get_company_concept(cik, candidate, taxonomy)
                if not data:
                    continue

                concept_data = data.get("units", {}).get(unit, [])
                if not concept_data:
                    continue

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
                    if entry.get("form") in allowed_forms
                    and (allowed_fp is None or entry.get("fp") in allowed_fp)
                ]

                if not filtered:
                    continue

                # Deduplicate restated figures
                filtered = self._deduplicate_entries(filtered)

                filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
                result = filtered[:periods]

                # Tag which concept actually matched
                for entry in result:
                    entry["concept_used"] = candidate

                if candidate != concept:
                    logger.info(
                        f"{ticker}: '{concept}' not found, "
                        f"used fallback '{candidate}'"
                    )
                return result

            except Exception as e:
                logger.error(
                    f"Failed to extract {candidate} for {ticker}: {e}"
                )
                continue

        return []

    def get_financial_ttm(
        self,
        ticker: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
    ) -> Optional[Dict[str, Any]]:
        """
        Compute a Trailing Twelve Months (TTM) value for an income statement
        or cash flow concept by summing the four most recent quarterly filings.

        For balance sheet / instantaneous concepts, returns the most recent
        quarterly value directly (TTM doesn't apply to point-in-time figures).

        Args:
            ticker: Stock ticker.
            concept: XBRL concept name (e.g. "Revenues", "NetIncomeLoss").
            taxonomy: XBRL taxonomy (default "us-gaap").
            unit: Unit filter (e.g. "USD", "USD/shares").

        Returns:
            Dict with keys: ttm_val, periods_used, latest_quarter_end,
            concept_used, is_instantaneous.  Or None if data unavailable.
        """
        is_instant = concept in self.INSTANTANEOUS_CONCEPTS

        if is_instant:
            # For balance sheet items, just return the latest quarter
            rows = self.get_financial_metric(
                ticker, concept, taxonomy=taxonomy, unit=unit,
                periods=1, form_types=["10-Q", "10-K"],
            )
            if not rows:
                return None
            return {
                "ttm_val": rows[0]["val"],
                "periods_used": 1,
                "latest_quarter_end": rows[0]["end"],
                "concept_used": rows[0].get("concept_used", concept),
                "is_instantaneous": True,
            }

        # Income/CF: fetch last 4 quarterly filings and sum them
        rows = self.get_financial_metric(
            ticker, concept, taxonomy=taxonomy, unit=unit,
            periods=4, form_types=["10-Q"],
        )

        if len(rows) < 4:
            # Fall back to annual if fewer than 4 quarters available
            annual = self.get_financial_metric(
                ticker, concept, taxonomy=taxonomy, unit=unit,
                periods=1, form_types=["10-K"],
            )
            if annual:
                r = annual[0]
                return {
                    "ttm_val": r["val"],
                    "periods_used": 1,
                    "latest_quarter_end": r["end"],
                    "concept_used": r.get("concept_used", concept),
                    "is_instantaneous": False,
                    "note": "Fewer than 4 quarters available — using most recent annual.",
                }
            return None

        ttm_val = sum(r["val"] for r in rows if r.get("val") is not None)
        return {
            "ttm_val": ttm_val,
            "periods_used": len(rows),
            "latest_quarter_end": rows[0]["end"],
            "quarters": [
                {"end": r["end"], "val": r["val"]} for r in rows
            ],
            "concept_used": rows[0].get("concept_used", concept),
            "is_instantaneous": False,
        }

    # ── XBRL Frames (cross-company comparison) ─────────────────────────
    def get_xbrl_frame(
        self,
        concept: str,
        period: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single XBRL concept for ALL companies for a given period.
        Returns one value per company — already deduplicated by the SEC.

        Args:
            concept: XBRL concept name (e.g. "Revenues", "Assets").
            period:  Calendar period string.  Format rules:
                     - Annual duration (income/CF):   "CY2023"
                     - Quarterly duration (income/CF): "CY2023Q4"
                     - Instantaneous (balance sheet):  "CY2023Q4I"
            taxonomy: XBRL taxonomy (default "us-gaap").
            unit: Unit of measure (e.g. "USD", "USD/shares", "shares").

        Returns:
            Dict with "data" list of {cik, entityName, val, end, ...} or None.
        """
        url = self.XBRL_FRAMES_URL.format(
            taxonomy=taxonomy, concept=concept, unit=unit, period=period,
        )
        try:
            return self._get(url).json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            logger.error(f"Frames request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Frames request failed: {e}")
            return None

    def compare_metric_across_companies(
        self,
        tickers: List[str],
        concept: str,
        year: int,
        quarter: Optional[int] = None,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
    ) -> List[Dict[str, Any]]:
        """
        Compare a single financial metric across multiple companies using
        the XBRL frames endpoint (one API call for all companies).

        For tickers not found in the primary calendar-period frame (typically
        companies with non-December fiscal year ends), falls back to individual
        per-company company-concept queries so no ticker is silently dropped.

        Args:
            tickers: List of ticker symbols.
            concept: XBRL concept name.
            year: Calendar year (e.g. 2023).
            quarter: Optional quarter (1-4). None = full year.
            taxonomy: XBRL taxonomy.
            unit: Unit of measure.

        Returns:
            List of dicts: {ticker, entity_name, val, concept_used, period}.
        """
        # Resolve tickers → CIKs
        cik_map: Dict[str, str] = {}
        for t in tickers:
            cik = self.get_cik(t)
            if cik:
                cik_map[t.upper()] = cik

        if not cik_map:
            return []

        # Build CIK → ticker reverse map (strip leading zeros for matching)
        cik_to_ticker = {int(cik): t for t, cik in cik_map.items()}

        # Determine the period string based on concept type
        concepts_to_try = self.CONCEPT_ALIASES.get(concept, [concept])
        if concept not in self.CONCEPT_ALIASES:
            concepts_to_try = [concept]

        results: List[Dict[str, Any]] = []
        concept_used_final = concept

        for candidate in concepts_to_try:
            is_instant = candidate in self.INSTANTANEOUS_CONCEPTS

            if is_instant:
                # Balance sheet: instantaneous point-in-time.
                # For non-December fiscal year companies, also try Q1-Q3
                # of the same year so we catch March/June/September year-ends.
                if quarter:
                    periods_to_try = [f"CY{year}Q{quarter}I"]
                else:
                    periods_to_try = [
                        f"CY{year}Q4I",  # December year-end (most common)
                        f"CY{year}Q3I",  # September year-end (e.g. Apple)
                        f"CY{year}Q2I",  # June year-end
                        f"CY{year}Q1I",  # March year-end
                    ]
            else:
                # Income / cash flow: duration-based
                if quarter:
                    periods_to_try = [f"CY{year}Q{quarter}"]
                else:
                    # Annual: CY{year} covers Dec year-ends.  Non-Dec filers
                    # won't appear; we catch them in the per-company fallback.
                    periods_to_try = [f"CY{year}"]

            # --- Batch frames pass ---
            found_ciks: set = set()
            for period in periods_to_try:
                frame_data = self.get_xbrl_frame(
                    candidate, period, taxonomy=taxonomy, unit=unit,
                )
                if not frame_data or not frame_data.get("data"):
                    continue

                for entry in frame_data["data"]:
                    entry_cik = entry.get("cik")
                    ticker = cik_to_ticker.get(entry_cik)
                    if ticker and ticker not in found_ciks:
                        found_ciks.add(ticker)
                        results.append({
                            "ticker": ticker,
                            "entity_name": entry.get("entityName", ""),
                            "val": entry.get("val"),
                            "end": entry.get("end", ""),
                            "concept_used": candidate,
                            "period": period,
                        })

            if results:
                concept_used_final = candidate
                if candidate != concept:
                    logger.info(
                        f"Frames: '{concept}' not found, "
                        f"used fallback '{candidate}'"
                    )
                break  # found data with this concept; stop alias iteration

        # --- Per-company fallback for any tickers still missing ---
        # This covers non-standard fiscal years not caught by the frames sweep.
        found_tickers = {r["ticker"] for r in results}
        missing_tickers = [t for t in cik_map if t not in found_tickers]

        for ticker in missing_tickers:
            logger.info(
                f"{ticker}: not in XBRL frames for {year}; "
                "trying per-company concept query"
            )
            # For annual queries, grab the most recent annual (10-K) near the target year
            form_filter = ["10-Q", "10-K"] if quarter else ["10-K"]
            rows = self.get_financial_metric(
                ticker, concept,
                taxonomy=taxonomy, unit=unit,
                periods=4,
                form_types=form_filter,
            )
            if not rows:
                continue

            # Pick the row whose fiscal year is closest to the requested year
            best = None
            for row in rows:
                row_year = int(row.get("end", "0000")[:4])
                if best is None:
                    best = row
                else:
                    best_year = int(best.get("end", "0000")[:4])
                    if abs(row_year - year) < abs(best_year - year):
                        best = row

            if best:
                results.append({
                    "ticker": ticker,
                    "entity_name": ticker,   # entity name unknown from this path
                    "val": best["val"],
                    "end": best["end"],
                    "concept_used": best.get("concept_used", concept),
                    "period": f"FY ending {best['end']} (non-Dec fiscal year)",
                    "fiscal_year_note": True,
                })

        return results

    # ── Filing text retrieval ──────────────────────────────────────────

    # Sections of interest in 10-K / 10-Q filings.
    # Regex patterns match common section headings in SEC filings.
    _SECTION_PATTERNS = [
        (r"item\s+1[\.\s]", "Item 1"),       # Business
        (r"item\s+1a[\.\s]", "Item 1A"),      # Risk Factors
        (r"item\s+7[\.\s]", "Item 7"),        # MD&A
        (r"item\s+7a[\.\s]", "Item 7A"),      # Market Risk
        (r"item\s+8[\.\s]", "Item 8"),        # Financial Statements
    ]

    def _clean_filing_html(self, html: str) -> str:
        """
        Extract readable text from an SEC filing HTML/iXBRL document.
        Uses BeautifulSoup to properly handle inline XBRL tags and
        produce clean, human-readable text.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, and hidden elements
        for tag in soup.find_all(["script", "style", "meta", "link"]):
            tag.decompose()

        # Remove XBRL-specific tags but keep their text content
        # (ix:nonNumeric, ix:nonFraction, ix:header, etc.)
        for tag in soup.find_all(re.compile(r"^ix:", re.IGNORECASE)):
            if tag.name and tag.name.lower() == "ix:header":
                # The ix:header block is pure XBRL metadata — remove entirely
                tag.decompose()
            else:
                # Replace the XBRL wrapper with its text content
                tag.unwrap()

        # Remove hidden div blocks (XBRL often hides metadata in these)
        for tag in soup.find_all(
            "div", style=re.compile(r"display\s*:\s*none", re.IGNORECASE)
        ):
            tag.decompose()

        # Get text, collapsing whitespace
        text = soup.get_text(separator=" ")
        # Collapse runs of whitespace, but preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text

    def _find_section_start(self, text: str) -> int:
        """
        Find where the actual business content starts by looking for
        common SEC filing section headings (Item 1, Item 1A, etc.).
        Returns the character offset, or 0 if no sections found.
        """
        text_lower = text.lower()
        best_pos = len(text)  # start with "no match"

        for pattern, _label in self._SECTION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match and match.start() < best_pos:
                best_pos = match.start()

        return best_pos if best_pos < len(text) else 0

    def get_filing_text(
        self, ticker: str, form_type: str = "10-K", max_chars: int = 15000
    ) -> Optional[Dict[str, str]]:
        """
        Fetch the most recent filing of a given type and return readable text.
        Uses BeautifulSoup to strip iXBRL markup and skips the XBRL preamble
        to start at actual business content.

        Args:
            ticker: Stock ticker symbol.
            form_type: SEC form type (default "10-K").
            max_chars: Max characters to return (default 15000).
        """
        filings = self.get_filings(ticker, form_types=[form_type], max_results=1)
        if not filings:
            return None

        filing = filings[0]
        try:
            resp = self._get(filing["url"])
            raw_html = resp.text

            # Clean the HTML/iXBRL into readable text
            clean = self._clean_filing_html(raw_html)

            # For 10-K and 10-Q, try to skip to the first section heading
            if form_type in ("10-K", "10-Q"):
                section_start = self._find_section_start(clean)
                if section_start > 0:
                    clean = clean[section_start:]

            # Truncate to requested size
            truncated = len(clean) > max_chars
            clean = clean[:max_chars]

            return {
                "form": filing["form"],
                "date": filing["date"],
                "url": filing["url"],
                "text": clean,
                "truncated": truncated,
            }
        except Exception as e:
            logger.error(f"Failed to fetch filing text for {ticker}: {e}")
            return None
