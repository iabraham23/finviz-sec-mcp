"""
SEC EDGAR Client — powered by edgartools.

Wraps the edgartools library (https://github.com/dgunning/edgartools) to
provide a clean, reliable interface for SEC filing data.  Replaces the
previous hand-rolled REST client with edgartools' typed objects, built-in
XBRL parsing, and automatic rate limiting.

Free public API — no key required.
"""

import logging
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from edgar import Company, set_identity

load_dotenv()

logger = logging.getLogger(__name__)

# SEC requires a contact email in User-Agent
_sec_email = os.getenv("SEC_EMAIL", "ia@cwcgroup.com")
set_identity(_sec_email)


# ── Helpers ───────────────────────────────────────────────────────────────

# Balance-sheet concepts are point-in-time; everything else is duration.
INSTANTANEOUS_CONCEPTS = {
    "Assets", "Liabilities", "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments", "Cash",
    "LongTermDebt", "LongTermDebtNoncurrent",
    "LongTermDebtAndCapitalLeaseObligations",
    "CommonStockSharesOutstanding",
}

# Maps user-friendly metric names to edgartools FactQuery concept patterns.
# edgartools' by_concept() supports regex, so we use a broad pattern for each
# metric and then pick the best match from results.
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
    "GrossProfit": ["GrossProfit"],
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
    "EarningsPerShareBasic": ["EarningsPerShareBasic"],
    "EarningsPerShareDiluted": ["EarningsPerShareDiluted"],
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


class EdgarClient:
    """Client for SEC EDGAR data via the edgartools library."""

    def __init__(self):
        # Company objects are cached by ticker to avoid repeated lookups
        self._company_cache: Dict[str, Company] = {}

    def _get_company(self, ticker: str) -> Optional[Company]:
        """Get or create a cached Company object for a ticker."""
        ticker = ticker.upper().strip()
        if ticker in self._company_cache:
            return self._company_cache[ticker]
        try:
            company = Company(ticker)
            self._company_cache[ticker] = company
            return company
        except Exception as e:
            logger.error(f"Failed to look up company {ticker}: {e}")
            return None

    # ── Filing list ──────────────────────────────────────────────────────

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
            form_types: Filter to specific forms (e.g. ["10-K", "10-Q"]).
            max_results: Maximum filings to return.
        """
        company = self._get_company(ticker)
        if not company:
            return []

        try:
            # Compute a 5-year lookback date for unfiltered queries to avoid
            # fetching the entire EDGAR submissions history (which can be
            # thousands of records for large-cap companies).
            import datetime as _dt
            _five_years_ago = (
                _dt.date.today() - _dt.timedelta(days=1825)
            ).isoformat()

            # Get filings, optionally filtered by form type.
            # edgartools v5+ accepts a list directly; for a single form or
            # multiple forms we can pass them all at once.
            if form_types:
                form_arg = form_types[0] if len(form_types) == 1 else form_types
                filings = company.get_filings(form=form_arg)
            else:
                # No form filter — limit to recent 5 years to keep the query
                # fast and avoid downloading the full submissions history.
                filings = company.get_filings(date=f"{_five_years_ago}:")

            results = []
            for f in filings:
                results.append({
                    "form": f.form,
                    "date": str(f.filing_date),
                    "accession": f.accession_no,
                    "description": getattr(f, "primary_doc_description", "") or "",
                    "url": f.homepage_url or "",
                })

                if len(results) >= max_results:
                    break

            return results

        except Exception as e:
            logger.error(f"Failed to get filings for {ticker}: {e}")
            return []

    # ── Filing text retrieval ────────────────────────────────────────────

    def get_filing_text(
        self, ticker: str, form_type: str = "10-K", max_chars: int = 15000
    ) -> Optional[Dict[str, str]]:
        """
        Fetch the most recent filing of a given type and return clean text.
        Uses edgartools' built-in text extraction which properly handles
        iXBRL markup without manual BeautifulSoup parsing.

        Args:
            ticker: Stock ticker symbol.
            form_type: SEC form type (default "10-K").
            max_chars: Max characters to return (default 15000).
        """
        company = self._get_company(ticker)
        if not company:
            return None

        try:
            filing = company.latest(form_type)
            if not filing:
                return None

            # edgartools .text() returns clean plaintext with XBRL stripped
            text = filing.text()
            if not text:
                return None

            # For 10-K/10-Q, skip to the first section heading
            if form_type in ("10-K", "10-Q"):
                section_start = self._find_section_start(text)
                if section_start > 0:
                    text = text[section_start:]

            truncated = len(text) > max_chars
            text = text[:max_chars]

            return {
                "form": filing.form,
                "date": str(filing.filing_date),
                "url": filing.homepage_url or "",
                "text": text,
                "truncated": truncated,
            }

        except Exception as e:
            logger.error(f"Failed to fetch filing text for {ticker}: {e}")
            return None

    # Section patterns for finding where content starts in 10-K/10-Q
    _SECTION_PATTERNS = [
        (r"item\s+1[\.\s]", "Item 1"),
        (r"item\s+1a[\.\s]", "Item 1A"),
        (r"item\s+7[\.\s]", "Item 7"),
        (r"item\s+7a[\.\s]", "Item 7A"),
        (r"item\s+8[\.\s]", "Item 8"),
    ]

    def _find_section_start(self, text: str) -> int:
        """Find where the actual business content starts."""
        text_lower = text.lower()
        best_pos = len(text)

        for pattern, _label in self._SECTION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match and match.start() < best_pos:
                best_pos = match.start()

        return best_pos if best_pos < len(text) else 0

    # ── Filing section extraction via TenK/TenQ objects ──────────────────

    # Section label map for display purposes
    _SECTION_LABELS = {
        "Item 1":  "Business",
        "Item 1A": "Risk Factors",
        "Item 1B": "Unresolved Staff Comments",
        "Item 2":  "Properties",
        "Item 3":  "Legal Proceedings",
        "Item 7":  "Management's Discussion and Analysis",
        "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
        "Item 8":  "Financial Statements",
        "Item 9A": "Controls and Procedures",
    }

    # Alias → canonical "Item X" name for get_filing_sections
    _SECTION_ALIASES: Dict[str, str] = {
        # Friendly lowercase aliases
        "mda": "Item 7",
        "risk_factors": "Item 1A",
        "business": "Item 1",
        # Short numeric forms (no "Item " prefix)
        "1": "Item 1",
        "1a": "Item 1A",
        "1b": "Item 1B",
        "1c": "Item 1C",
        "2": "Item 2",
        "3": "Item 3",
        "7": "Item 7",
        "7a": "Item 7A",
        "8": "Item 8",
        "9a": "Item 9A",
    }

    @classmethod
    def _resolve_section(cls, name: str) -> str:
        """Normalise a user-supplied section name to canonical 'Item X' form."""
        key = name.strip().lower()
        if key in cls._SECTION_ALIASES:
            return cls._SECTION_ALIASES[key]
        # Already looks like "Item N" (case-insensitive) – normalise capitalisation
        m = re.match(r'^item\s+(.+)$', key)
        if m:
            return f"Item {m.group(1).upper()}"
        return name  # pass through unchanged

    def get_filing_sections(
        self,
        ticker: str,
        form_type: str = "10-K",
        sections: Optional[List[str]] = None,
        max_chars_per_section: int = 8000,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch specific named sections from a 10-K or 10-Q filing using
        edgartools' structured TenK/TenQ objects.  Returns clean prose text
        for each requested section without iXBRL preamble overhead.

        Falls back to the raw-text approach for non-annual/quarterly forms
        (e.g. 8-K) or if the structured object cannot be built.

        Args:
            ticker: Stock ticker symbol.
            form_type: SEC form type (default "10-K").
            sections: List of item names to fetch.  Supports full names
                ("Item 7"), short numbers ("7", "1A"), and friendly aliases
                ("mda", "risk_factors", "business").
                Default: ["Item 7", "Item 1A"] (MD&A + Risk Factors).
            max_chars_per_section: Max characters per section (default 8000).
        """
        if sections is None:
            sections = ["Item 7", "Item 1A"]

        # Resolve aliases / short forms to canonical "Item X" names.
        # Keep the original user-supplied name as the key in the output so
        # the caller sees what they asked for.
        resolved: Dict[str, str] = {s: self._resolve_section(s) for s in sections}

        company = self._get_company(ticker)
        if not company:
            return None

        try:
            filing = company.latest(form_type)
            if not filing:
                return None

            # Only attempt structured section access for 10-K / 10-Q
            if form_type in ("10-K", "10-Q"):
                try:
                    obj = filing.obj()
                    if obj is not None:
                        available_items = []
                        try:
                            # Deduplicate while preserving order
                            raw_items = list(obj.items)
                            seen: set = set()
                            for item in raw_items:
                                key = str(item)
                                if key not in seen:
                                    seen.add(key)
                                    available_items.append(item)
                        except Exception:
                            pass

                        extracted: Dict[str, str] = {}
                        for orig_name, canonical in resolved.items():
                            try:
                                text = obj[canonical]
                                if text:
                                    text = str(text)
                                    truncated = len(text) > max_chars_per_section
                                    text = text[:max_chars_per_section]
                                    if truncated:
                                        text += f"\n[Truncated to {max_chars_per_section:,} chars — pass a larger max_chars_per_section for more]"
                                    extracted[orig_name] = text
                            except Exception as e:
                                logger.debug(
                                    f"Section '{canonical}' not found in {ticker} "
                                    f"{form_type}: {e}"
                                )

                        return {
                            "form": filing.form,
                            "date": str(filing.filing_date),
                            "url": filing.homepage_url or "",
                            "sections": extracted,
                            "available_items": available_items,
                            "method": "structured",
                        }
                except Exception as e:
                    logger.warning(
                        f"Could not build structured object for {ticker} "
                        f"{form_type}, falling back to text: {e}"
                    )

            # Fallback: raw text — cap at a reasonable limit regardless of
            # how many sections were requested to avoid huge EDGAR downloads.
            total_chars = min(max_chars_per_section * len(sections), 12000)
            raw = self.get_filing_text(ticker, form_type=form_type, max_chars=total_chars)
            if raw:
                raw["sections"] = {"text": raw.pop("text", "")}
                raw["available_items"] = []
                raw["method"] = "raw_text"
            return raw

        except Exception as e:
            logger.error(f"Failed to fetch filing sections for {ticker}: {e}")
            return None

    # ── Financial metrics via FactQuery ──────────────────────────────────

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
        Extract a specific financial metric from XBRL data using edgartools'
        FactQuery API with concept alias fallback chains.

        Tries all concept aliases and picks the one with the most recent data,
        ensuring ASC 606 revenue tags are preferred over deprecated ones.

        Args:
            ticker: Stock ticker.
            concept: Metric name (e.g. "Revenues", "NetIncomeLoss").
            taxonomy: XBRL taxonomy (default "us-gaap").
            unit: Unit filter (e.g. "USD", "USD/shares").
            periods: Number of recent periods to return.
            form_types: Restrict to specific form types, e.g. ["10-K"].

        Returns:
            List of dicts with keys: end, val, form, fy, fp, filed, concept_used.
        """
        company = self._get_company(ticker)
        if not company:
            return []

        # Build allowed forms and fiscal-period filters
        allowed_forms = set(form_types) if form_types else {"10-K", "10-Q"}

        if form_types and set(form_types) == {"10-K"}:
            allowed_fp = {"FY"}
        elif form_types and set(form_types) == {"10-Q"}:
            allowed_fp = {"Q1", "Q2", "Q3", "Q4"}
        else:
            allowed_fp = None

        # Build concept fallback chain
        concepts_to_try = CONCEPT_ALIASES.get(concept, [concept])

        try:
            facts = company.get_facts()
        except Exception as e:
            logger.error(f"Failed to get facts for {ticker}: {e}")
            return []

        # Try ALL concept aliases and pick the one with the most recent data.
        # This is critical because e.g. "Revenues" only has data through 2018
        # while "RevenueFromContractWithCustomerExcludingAssessedTax" has
        # current data after ASC 606 adoption.
        best_candidate = None
        best_df = None
        best_max_date = None

        for candidate in concepts_to_try:
            try:
                # Build query with form type filter applied via edgartools API
                query = facts.query().by_concept(candidate)

                # Apply form type filter via edgartools if single form
                if form_types and len(form_types) == 1:
                    query = query.by_form_type(form_types[0])

                df = query.to_dataframe()
                if df is None or df.empty:
                    continue

                # Filter to matching form types (for multi-form or unfiltered)
                if "form_type" in df.columns and (not form_types or len(form_types) > 1):
                    df = df[df["form_type"].isin(allowed_forms)]

                # Filter to matching fiscal periods
                if allowed_fp and "fiscal_period" in df.columns:
                    df = df[df["fiscal_period"].isin(allowed_fp)]

                # Filter to matching unit — edgartools uses different
                # unit strings than the raw SEC API (e.g. "USD per share"
                # instead of "USD/shares")
                if "unit" in df.columns:
                    unit_map = {
                        "USD/shares": ["USD/shares", "USD per share"],
                        "shares": ["shares"],
                        "USD": ["USD"],
                    }
                    acceptable_units = unit_map.get(unit, [unit])
                    df = df[df["unit"].isin(acceptable_units)]

                # For quarterly data (10-Q), filter out year-to-date
                # cumulative figures.  10-Q filings contain BOTH single-
                # quarter values (≤100 day duration) AND cumulative YTD
                # values (6-9 month spans).  We only want single quarters.
                if (allowed_fp and allowed_fp != {"FY"}
                        and "period_start" in df.columns
                        and "period_end" in df.columns):
                    try:
                        import pandas as pd
                        ps = pd.to_datetime(df["period_start"])
                        pe = pd.to_datetime(df["period_end"])
                        duration_days = (pe - ps).dt.days
                        # Single quarter ≈ 90 days; allow up to 100
                        df = df[duration_days <= 100]
                    except Exception:
                        pass  # fall through if date parsing fails

                if df.empty:
                    continue

                # Check the most recent date for this concept
                if "period_end" in df.columns:
                    max_date = df["period_end"].max()
                    if best_max_date is None or max_date > best_max_date:
                        best_max_date = max_date
                        best_candidate = candidate
                        best_df = df
                else:
                    # No period_end column — take what we can get
                    if best_df is None:
                        best_candidate = candidate
                        best_df = df

            except Exception as e:
                logger.error(f"Failed to query {candidate} for {ticker}: {e}")
                continue

        if best_df is None or best_candidate is None:
            return []

        df = best_df

        # Deduplicate: many concepts have dimensional breakdowns (segments,
        # geography, etc.) that produce multiple entries per period_end.
        # For financial totals, the largest absolute value per period is
        # typically the consolidated total.  We pick the max-value entry.
        if "period_end" in df.columns and "numeric_value" in df.columns:
            df = df.sort_values("numeric_value", ascending=False)
            df = df.drop_duplicates(subset=["period_end"], keep="first")

        # Sort by period end descending and limit
        if "period_end" in df.columns:
            df = df.sort_values("period_end", ascending=False)

        df = df.head(periods)

        # Build result dicts matching the API contract
        results = []
        for _, row in df.iterrows():
            results.append({
                "end": str(row.get("period_end", "")),
                "val": row.get("numeric_value") if "numeric_value" in df.columns else row.get("value"),
                "form": row.get("form_type", ""),
                "fy": row.get("fiscal_year", ""),
                "fp": row.get("fiscal_period", ""),
                "filed": str(row.get("filing_date", "")),
                "concept_used": best_candidate,
            })

        if results and best_candidate != concept:
            logger.info(
                f"{ticker}: '{concept}' not found or stale, "
                f"using '{best_candidate}' (most recent data)"
            )

        return results

    # ── TTM computation ──────────────────────────────────────────────────

    def get_financial_ttm(
        self,
        ticker: str,
        concept: str,
        taxonomy: str = "us-gaap",
        unit: str = "USD",
    ) -> Optional[Dict[str, Any]]:
        """
        Compute a Trailing Twelve Months (TTM) value for an income statement
        or cash flow concept by summing four most recent quarterly filings.
        For balance sheet items, returns the most recent quarterly value.
        """
        is_instant = concept in INSTANTANEOUS_CONCEPTS

        if is_instant:
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

        # Income/CF: sum last 4 quarterly filings
        rows = self.get_financial_metric(
            ticker, concept, taxonomy=taxonomy, unit=unit,
            periods=4, form_types=["10-Q"],
        )

        if len(rows) < 4:
            # Fall back to annual
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
        ttm_end = rows[0]["end"]

        # If a more-recent annual (10-K) has been filed since the last 10-Q,
        # it contains Q4 data that our 10-Q sum can never include.  In that
        # case the annual IS the TTM and is strictly more current.
        annual = self.get_financial_metric(
            ticker, concept, taxonomy=taxonomy, unit=unit,
            periods=1, form_types=["10-K"],
        )
        if annual:
            annual_end = annual[0]["end"]
            # ISO-8601 strings compare correctly as plain strings
            if annual_end > ttm_end:
                return {
                    "ttm_val": annual[0]["val"],
                    "periods_used": 1,
                    "latest_quarter_end": annual_end,
                    "concept_used": annual[0].get("concept_used", concept),
                    "is_instantaneous": False,
                    "note": (
                        f"FY annual (10-K ending {annual_end}) is more current "
                        f"than 4Q TTM (ending {ttm_end}); Q4 now included."
                    ),
                }

        return {
            "ttm_val": ttm_val,
            "periods_used": len(rows),
            "latest_quarter_end": ttm_end,
            "quarters": [
                {"end": r["end"], "val": r["val"]} for r in rows
            ],
            "concept_used": rows[0].get("concept_used", concept),
            "is_instantaneous": False,
        }

    # ── Cross-company comparison ─────────────────────────────────────────

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
        Compare a single financial metric across multiple companies.
        Uses per-company FactQuery lookups (edgartools handles caching
        and rate limiting internally).
        """
        results: List[Dict[str, Any]] = []

        for ticker in tickers:
            ticker = ticker.upper().strip()
            company = self._get_company(ticker)
            if not company:
                continue

            # Determine form types and periods to look for
            if quarter:
                form_filter = ["10-Q"]
            else:
                form_filter = ["10-K"]

            rows = self.get_financial_metric(
                ticker, concept,
                taxonomy=taxonomy, unit=unit,
                periods=6,  # get enough to find the right year
                form_types=form_filter,
            )
            if not rows:
                continue

            # Find the row closest to the requested year
            best = None
            for row in rows:
                row_year = int(row.get("end", "0000")[:4])
                if quarter:
                    # For quarterly, match year AND try to find right quarter
                    row_fp = row.get("fp", "")
                    if row_year == year and row_fp == f"Q{quarter}":
                        best = row
                        break
                else:
                    # For annual, find closest fiscal year
                    if best is None:
                        best = row
                    else:
                        best_year = int(best.get("end", "0000")[:4])
                        if abs(row_year - year) < abs(best_year - year):
                            best = row

            if best:
                fy_note = False
                end_year = int(best.get("end", "0000")[:4])
                if not quarter and end_year != year:
                    fy_note = True

                results.append({
                    "ticker": ticker,
                    "entity_name": getattr(company, "name", ticker),
                    "val": best["val"],
                    "end": best["end"],
                    "concept_used": best.get("concept_used", concept),
                    "period": f"FY ending {best['end']}" if not quarter else f"Q{quarter} {year}",
                    "fiscal_year_note": fy_note,
                })

        return results

    # ── Financials via edgartools' Financials API ────────────────────────

    def get_financial_statements(
        self,
        ticker: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get structured financial statements (income, balance sheet,
        cash flow) using edgartools' Financials API.

        Returns a dict with keys: income_statement, balance_sheet,
        cashflow_statement — each containing a DataFrame-ready structure.
        """
        company = self._get_company(ticker)
        if not company:
            return None

        try:
            financials = company.get_financials()
            result = {}

            for stmt_name, method_name in [
                ("income_statement", "income_statement"),
                ("balance_sheet", "balance_sheet"),
                ("cashflow_statement", "cashflow_statement"),
            ]:
                try:
                    stmt = getattr(financials, method_name)()
                    df = stmt.to_dataframe()

                    # Get period columns (date strings like "2024-09-28")
                    date_cols = sorted(
                        [c for c in df.columns if re.match(r"^\d{4}-\d{2}-\d{2}$", str(c))],
                        reverse=True,
                    )

                    rows = []
                    for _, row in df.iterrows():
                        is_abstract = row.get("abstract", False)
                        if is_abstract:
                            continue
                        entry = {
                            "label": row.get("label", ""),
                            "concept": row.get("concept", ""),
                        }
                        for d in date_cols:
                            entry[d] = row.get(d)
                        rows.append(entry)

                    result[stmt_name] = {
                        "periods": date_cols,
                        "rows": rows,
                    }
                except Exception as e:
                    logger.warning(f"Could not get {stmt_name} for {ticker}: {e}")
                    result[stmt_name] = None

            # Also grab quick metrics
            try:
                result["quick_metrics"] = {
                    "revenue": financials.get_revenue(),
                    "net_income": financials.get_net_income(),
                    "operating_income": financials.get_operating_income(),
                    "total_assets": financials.get_total_assets(),
                    "total_liabilities": financials.get_total_liabilities(),
                    "stockholders_equity": financials.get_stockholders_equity(),
                    "operating_cash_flow": financials.get_operating_cash_flow(),
                    "free_cash_flow": financials.get_free_cash_flow(),
                    "capital_expenditures": financials.get_capital_expenditures(),
                }
            except Exception as e:
                logger.warning(f"Could not get quick metrics for {ticker}: {e}")
                result["quick_metrics"] = None

            return result

        except Exception as e:
            logger.error(f"Failed to get financial statements for {ticker}: {e}")
            return None

    # ── Insider filings with structured data ─────────────────────────────

    def get_insider_filings_detailed(
        self,
        ticker: str,
        max_results: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Get insider trading filings (Form 3/4/5) with structured data
        parsed from the XBRL-tagged filing via edgartools' Form4 objects.
        """
        company = self._get_company(ticker)
        if not company:
            return []

        results = []
        try:
            for form_type in ["4", "3", "5"]:
                try:
                    filings = company.get_filings(form=form_type)
                except Exception:
                    continue

                for f in filings:
                    if len(results) >= max_results:
                        break

                    entry = {
                        "form": f.form,
                        "date": str(f.filing_date),
                        "url": f.homepage_url or "",
                    }

                    # Try to parse the filing as a typed object
                    try:
                        obj = f.obj()
                        if hasattr(obj, "insider_name"):
                            entry["insider_name"] = obj.insider_name or ""
                        if hasattr(obj, "position"):
                            entry["position"] = obj.position or ""
                        if hasattr(obj, "shares_traded"):
                            entry["shares_traded"] = obj.shares_traded

                        # Get ownership summary if available
                        if hasattr(obj, "get_ownership_summary"):
                            try:
                                summary = obj.get_ownership_summary()
                                entry["activity"] = summary.primary_activity
                                entry["net_change"] = summary.net_change
                                entry["net_value"] = summary.net_value
                                entry["remaining_shares"] = summary.remaining_shares
                            except Exception:
                                pass
                    except Exception:
                        pass

                    results.append(entry)

                if len(results) >= max_results:
                    break

        except Exception as e:
            logger.error(f"Failed to get insider filings for {ticker}: {e}")

        return results
