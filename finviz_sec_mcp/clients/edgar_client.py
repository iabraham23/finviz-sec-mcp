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
from edgar.standardization import get_synonym_groups # type: ignore

load_dotenv()

logger = logging.getLogger(__name__)

# SEC requires a contact email in User-Agent
_sec_email = os.getenv("SEC_EMAIL", "ia@cwcgroup.com")
set_identity(_sec_email)


# ── Helpers ───────────────────────────────────────────────────────────────

# Singleton SynonymGroups instance — 59 curated synonym groups covering
# all common financial concepts.  Used as the fallback alias source
# instead of a hand-maintained dict.
_synonym_groups = get_synonym_groups()

# Balance-sheet synonym group names — concepts in these groups are
# point-in-time (instantaneous) rather than period-based.
_BALANCE_SHEET_GROUPS = {
    "total_assets", "total_liabilities", "stockholders_equity",
    "cash_and_equivalents", "long_term_debt", "short_term_debt",
    "common_shares_outstanding", "goodwill", "intangible_assets",
    "accounts_receivable", "inventory", "prepaid_expenses",
    "total_current_assets", "property_plant_equipment",
    "long_term_investments", "short_term_investments",
    "deferred_tax_assets", "accounts_payable", "accrued_liabilities",
    "deferred_revenue", "total_current_liabilities",
    "deferred_tax_liabilities", "common_stock",
    "additional_paid_in_capital", "retained_earnings", "treasury_stock",
    "accumulated_other_comprehensive_income",
    "operating_lease_liability", "operating_lease_right_of_use_asset",
    "finance_lease_liability",
}

ANNUAL_FORM_TYPES = ("10-K", "20-F", "40-F")
QUARTERLY_FORM_TYPES = ("10-Q",)

# Manual concept aliases for metrics that frequently differ across
# IFRS/private-issuer filings and are not covered well by SynonymGroups.
MANUAL_CONCEPT_ALIASES: Dict[str, List[str]] = {
    "WeightedAverageNumberOfDilutedSharesOutstanding": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfOrdinarySharesOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfOrdinarySharesOutstandingDiluted",
        "WeightedAverageNumberOfSharesOutstandingDiluted",
        # Basic weighted-average share concepts are a usable fallback when
        # diluted shares are not tagged separately in 20-F IFRS filings.
        "WeightedAverageNumberOfOrdinarySharesOutstanding",
        "WeightedAverageNumberOfSharesOutstanding",
        "WeightedAverageNumberOfOrdinarySharesBasic",
        "WeightedAverageNumberOfSharesBasic",
    ],
    "NetCashProvidedByUsedInOperatingActivities": [
        "NetCashProvidedByUsedInOperatingActivities",
        "CashFlowsFromUsedInOperatingActivities",
    ],
}


def _is_instantaneous(concept: str) -> bool:
    """Check if an XBRL concept represents a point-in-time (balance sheet) item.

    Uses the edgartools SynonymGroups system to identify the concept's
    financial statement category, falling back to a name-based heuristic.
    """
    info = _synonym_groups.identify_concept(concept)
    if info and info.group.name in _BALANCE_SHEET_GROUPS:
        return True
    # Heuristic fallback for concepts not in synonym groups
    if info and info.group.category == "balance_sheet":
        return True
    return False


def _form_filter_kind(form_types: Optional[List[str]]) -> str:
    """Classify a form filter as annual, quarterly, or mixed."""
    if not form_types:
        return "mixed"

    form_set = {form.upper() for form in form_types}
    if form_set.issubset(set(ANNUAL_FORM_TYPES)):
        return "annual"
    if form_set.issubset(set(QUARTERLY_FORM_TYPES)):
        return "quarterly"
    return "mixed"


def _get_manual_aliases(concept: str) -> List[str]:
    """Return curated fallback aliases for concepts with known IFRS variants."""
    return MANUAL_CONCEPT_ALIASES.get(concept, [])


def _strip_concept_namespace(concept: str) -> str:
    """Normalize XBRL concept names by dropping common namespace separators."""
    return concept.split(":")[-1].split("_")[-1]

# Maps our user-facing metric names to the edgartools standard_concept names
# used in Financials API statement DataFrames.  The Financials API normalises
# every company's XBRL concepts to these standard names, so we can discover
# the *actual* concept at runtime instead of maintaining hardcoded alias lists.
#
# Each entry maps: user_metric → (standard_concept, statement_type)
# statement_type is one of "IS" (income), "BS" (balance sheet), "CF" (cash flow).
METRIC_TO_STANDARD: Dict[str, tuple] = {
    "Revenues":                                     ("Revenue", "IS"),
    "NetIncomeLoss":                                ("NetIncome", "IS"),
    "OperatingIncomeLoss":                          ("OperatingIncomeLoss", "IS"),
    "GrossProfit":                                  ("GrossProfit", "IS"),
    "SellingGeneralAndAdministrativeExpense":        ("SellingGeneralAndAdminExpenses", "IS"),
    "ResearchAndDevelopmentExpense":                 ("ResearchAndDevelopementExpenses", "IS"),
    "IncomeTaxExpenseBenefit":                       ("IncomeTaxes", "IS"),
    "EarningsPerShareBasic":                        ("EarningsPerShareBasic", "IS"),
    "EarningsPerShareDiluted":                      ("EarningsPerShareDiluted", "IS"),
    "Assets":                                       ("Assets", "BS"),
    "Liabilities":                                  ("Liabilities", "BS"),
    "StockholdersEquity":                           ("AllEquityBalance", "BS"),
    "LongTermDebt":                                 ("LongTermDebt", "BS"),
    "CashAndCashEquivalentsAtCarryingValue":        ("CashAndMarketableSecurities", "BS"),
    "Goodwill":                                     ("Goodwill", "BS"),
    "IntangibleAssetsNetExcludingGoodwill":         ("IntangibleAssetsNetExcludingGoodwill", "BS"),
    "CommonStockSharesOutstanding":                 ("SharesYearEnd", "BS"),
    "WeightedAverageNumberOfDilutedSharesOutstanding": ("SharesFullyDilutedAverage", "IS"),
    "NetCashProvidedByUsedInOperatingActivities":   ("NetCashFromOperatingActivities", "CF"),
    "NetCashProvidedByUsedInFinancingActivities":   ("NetCashFromFinancingActivities", "CF"),
    "NetCashProvidedByUsedInInvestingActivities":   ("NetCashFromInvestingActivities", "CF"),
    "DepreciationDepletionAndAmortization":         ("DepreciationExpense", "CF"),
    "CapitalExpenditure":                           ("CapitalExpenses", "CF"),
    "PaymentsOfDividends":                          ("DistributionsToMinorityInterests", "CF"),
}

# Maps user-facing metric names → edgartools synonym group names.
# The SynonymGroups system provides curated alias lists for each group,
# so we no longer need to maintain our own CONCEPT_ALIASES dict.
# Entries with None mean the concept isn't in a synonym group and must
# rely on Financials API discovery or the raw concept name.
METRIC_TO_SYNONYM_GROUP: Dict[str, Optional[str]] = {
    "Revenues":                                         "revenue",
    "NetIncomeLoss":                                    "net_income",
    "OperatingIncomeLoss":                              "operating_income",
    "GrossProfit":                                      "gross_profit",
    "SellingGeneralAndAdministrativeExpense":            "sga_expense",
    "ResearchAndDevelopmentExpense":                     "research_and_development",
    "InterestExpense":                                  "interest_expense",
    "IncomeTaxExpenseBenefit":                           "income_tax_expense",
    "EarningsPerShareBasic":                            "earnings_per_share_basic",
    "EarningsPerShareDiluted":                          "earnings_per_share_diluted",
    "LongTermDebt":                                     "long_term_debt",
    "CashAndCashEquivalentsAtCarryingValue":            "cash_and_equivalents",
    "StockholdersEquity":                               "stockholders_equity",
    "NetCashProvidedByUsedInOperatingActivities":       "operating_cash_flow",
    "NetCashProvidedByUsedInFinancingActivities":       "financing_cash_flow",
    "NetCashProvidedByUsedInInvestingActivities":       "investing_cash_flow",
    "PaymentsOfDividends":                              "dividends_paid",
    "DepreciationDepletionAndAmortization":             "depreciation_and_amortization",
    "CapitalExpenditure":                               "capex",
    "Goodwill":                                         "goodwill",
    "IntangibleAssetsNetExcludingGoodwill":             "intangible_assets",
    "Assets":                                           "total_assets",
    "Liabilities":                                      "total_liabilities",
    "CommonStockSharesOutstanding":                     "common_shares_outstanding",
    # These two aren't in a synonym group — rely on discovery + raw name
    "WeightedAverageNumberOfDilutedSharesOutstanding":  None,
}


def _get_synonym_aliases(concept: str) -> List[str]:
    """Get fallback alias list for a concept from edgartools SynonymGroups.

    Returns the synonym group's full alias list if the concept maps to a
    known group, otherwise tries reverse lookup (identify the concept by
    its XBRL tag name), and falls back to just [concept] if nothing found.
    """
    # 1. Direct mapping from our metric name → group name
    group_name = METRIC_TO_SYNONYM_GROUP.get(concept)
    if group_name:
        try:
            return _synonym_groups.get_synonyms(group_name)
        except Exception:
            pass

    # 2. Reverse lookup — maybe the concept itself is a known XBRL tag
    info = _synonym_groups.identify_concept(concept)
    if info:
        return info.group.synonyms

    # 3. No synonym group found — return just the raw concept
    return [concept]


class EdgarClient:
    """Client for SEC EDGAR data via the edgartools library."""

    def __init__(self):
        # Company objects are cached by ticker to avoid repeated lookups
        self._company_cache: Dict[str, Company] = {}
        # Cache: (ticker, metric) → actual XBRL concept name
        self._concept_cache: Dict[tuple, str] = {}

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

    def _discover_concepts(self, ticker: str) -> Dict[str, str]:
        """Use the Financials API to discover actual XBRL concepts for a company.

        Reads the latest 10-K's income statement, balance sheet, and cash flow
        statement, then builds a mapping from our user-facing metric names to
        the exact XBRL concept the company uses.  Results are cached per ticker.

        Returns:
            Dict mapping user metric name → XBRL concept name.
        """
        cache_key = ticker.upper()
        # Check if we already have a full discovery for this ticker
        existing = {k[1]: v for k, v in self._concept_cache.items()
                    if k[0] == cache_key}
        if existing:
            return existing

        company = self._get_company(ticker)
        if not company:
            return {}

        result: Dict[str, str] = {}
        try:
            financials = company.get_financials()
        except Exception as e:
            logger.debug(f"Financials API unavailable for {ticker}: {e}")
            return {}

        # Map statement_type codes to Financials API methods
        stmt_methods = {
            "IS": financials.income_statement,
            "BS": financials.balance_sheet,
            "CF": financials.cash_flow_statement,
        }

        # Load each statement and build a standard_concept → xbrl_concept map
        std_to_xbrl: Dict[str, str] = {}
        for stmt_type, method in stmt_methods.items():
            try:
                stmt = method()
                df = stmt.to_dataframe()
                for _, row in df.iterrows():
                    if row.get("abstract"):
                        continue
                    std = row.get("standard_concept", "")
                    concept = row.get("concept", "")
                    if std and concept:
                        # Strip "us-gaap_" prefix to get raw concept name
                        xbrl = concept.replace("us-gaap_", "")
                        std_to_xbrl[std] = xbrl
            except Exception as e:
                logger.debug(f"Failed to load {stmt_type} for {ticker}: {e}")

        if not std_to_xbrl:
            return {}

        # Map our metric names → actual XBRL concepts via standard_concept
        for metric, (std_name, _stmt_type) in METRIC_TO_STANDARD.items():
            xbrl = std_to_xbrl.get(std_name)
            if xbrl:
                result[metric] = xbrl
                self._concept_cache[(cache_key, metric)] = xbrl

        logger.info(f"Discovered {len(result)} concepts for {ticker}")
        return result

    def _get_concepts_to_try(
        self, ticker: str, concept: str
    ) -> List[str]:
        """Get ordered list of XBRL concepts to try for a metric.

        Priority:
        1. Dynamically discovered concept from the company's latest 10-K
        2. Fallback aliases from edgartools SynonymGroups (59 curated groups)
        3. The raw concept name itself
        """
        ticker_upper = ticker.upper()
        concepts: List[str] = []

        # 1. Try cached / discovered concept first
        cache_key = (ticker_upper, concept)
        if cache_key in self._concept_cache:
            concepts.append(self._concept_cache[cache_key])
        else:
            # Run discovery (results are cached for subsequent calls)
            discovered = self._discover_concepts(ticker)
            if concept in discovered:
                concepts.append(discovered[concept])

        # 2. Add curated aliases for concepts with common IFRS variants.
        for alias in _get_manual_aliases(concept):
            if alias not in concepts:
                concepts.append(alias)

        # 3. Add fallback aliases from edgartools SynonymGroups
        for alias in _get_synonym_aliases(concept):
            if alias not in concepts:
                concepts.append(alias)

        # 4. Ensure the raw concept name is always tried
        if concept not in concepts:
            concepts.append(concept)

        return concepts

    def _discover_weighted_share_concept_from_latest_annual_filing(
        self,
        ticker: str,
    ) -> Optional[str]:
        """Discover the exact weighted-share concept from the latest annual filing XBRL.

        This is a lightweight fallback for foreign private issuers where
        companyfacts does not expose the share denominator under the
        expected concept name. Once discovered, the concept is cached and
        the normal companyfacts query path can fetch the full history.
        """
        company = self._get_company(ticker)
        if not company:
            return None

        try:
            form_arg = list(ANNUAL_FORM_TYPES)
            filings = company.get_filings(form=form_arg)
        except Exception as e:
            logger.error(f"Failed to get annual filings for {ticker}: {e}")
            return None

        try:
            filing = next(iter(filings), None)
        except Exception:
            filing = None
        if not filing:
            return None

        try:
            xbrl = filing.xbrl()
            if not xbrl:
                return None

            df = xbrl.facts.query().by_concept("WeightedAverage").to_dataframe()
            if df is None or df.empty:
                return None

            best_concept = None
            best_score = None

            for _, row in df.iterrows():
                concept = str(row.get("concept", "") or "")
                label = str(row.get("label", "") or "")
                numeric = row.get("numeric_value")
                period_end = row.get("period_end")
                period_start = row.get("period_start")
                period_type = str(row.get("period_type", "") or "")
                unit_ref = str(row.get("unit_ref", "") or "")

                if numeric is None or period_end is None:
                    continue
                if period_type != "duration":
                    continue
                if unit_ref.lower() != "shares":
                    continue

                haystack = f"{concept} {label}".lower()
                if "share" not in haystack:
                    continue
                if "exercise price" in haystack or "option" in haystack:
                    continue
                if "weightedaverage" not in haystack and "weighted average" not in haystack:
                    continue

                if period_start is not None:
                    try:
                        duration_days = (
                            date.fromisoformat(str(period_end))
                            - date.fromisoformat(str(period_start))
                        ).days
                        if duration_days < 300:
                            continue
                    except Exception:
                        pass

                score = 0
                if "diluted" in haystack or "adjustedweightedaverageshares" in haystack:
                    score += 2
                if "basic" in haystack:
                    score += 1

                if best_score is None or score > best_score:
                    best_score = score
                    best_concept = concept

            if best_concept:
                self._concept_cache[(ticker.upper(), "WeightedAverageNumberOfDilutedSharesOutstanding")] = best_concept
                logger.info(
                    f"{ticker}: discovered weighted-share concept from latest annual filing: "
                    f"{best_concept}"
                )
            return best_concept
        except Exception as e:
            logger.debug(f"Failed to inspect latest annual filing XBRL share concept for {ticker}: {e}")
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
        Prefers edgartools' markdown extraction for HTML/iXBRL filings,
        which is materially better for 20-F narrative content than the
        raw plaintext fallback.

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

            text = self._get_filing_markdown_or_text(filing)
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

    def _get_filing_markdown_or_text(self, filing: Any) -> Optional[str]:
        """Get the cleanest narrative text available for a filing.

        Preference order:
        1. Primary HTML attachment rendered as markdown
        2. Filing-level markdown rendering
        3. Filing plaintext
        """
        try:
            attachments = getattr(filing, "attachments", None)
            primary_html = getattr(attachments, "primary_html_document", None)
            if primary_html is not None:
                try:
                    markdown = primary_html.markdown()
                    if markdown:
                        return str(markdown)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            markdown = filing.markdown()
            if markdown:
                return str(markdown)
        except Exception:
            pass

        try:
            text = filing.text()
            if text:
                return str(text)
        except Exception:
            pass

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

    _SECTION_20F_ALIASES: Dict[str, str] = {
        "risk_factors": "Item 3.D",
        "risk": "Item 3.D",
        "3d": "Item 3.D",
        "business": "Item 4",
        "4": "Item 4",
        "mda": "Item 5",
        "operating_financial_review": "Item 5",
        "operating_and_financial_review": "Item 5",
        "5": "Item 5",
        "financial_statements": "Item 18",
        "17": "Item 17",
        "18": "Item 18",
    }

    _SECTION_20F_LABELS: Dict[str, str] = {
        "Item 3.D": "Risk Factors",
        "Item 4": "Information on the Company",
        "Item 5": "Operating and Financial Review and Prospects",
        "Item 17": "Financial Statements",
        "Item 18": "Financial Statements",
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

    @classmethod
    def _resolve_20f_section(cls, name: str) -> str:
        """Normalise a user-supplied 20-F section to canonical item form."""
        key = name.strip().lower()
        if key in cls._SECTION_20F_ALIASES:
            return cls._SECTION_20F_ALIASES[key]
        m = re.match(r"^item\s+(.+)$", key)
        if m:
            return f"Item {m.group(1).upper()}"
        return name

    def _extract_item_section_from_markdown(
        self, text: str, canonical_item: str, max_chars: int
    ) -> Optional[str]:
        """Extract a filing item or item subsection from markdown text."""
        section_text = self._extract_item_block_from_markdown(text, canonical_item)
        if not section_text:
            return None

        truncated = len(section_text) > max_chars
        section_text = section_text[:max_chars]
        if truncated:
            section_text += (
                f"\n[Truncated to {max_chars:,} chars — pass a larger "
                f"max_chars_per_section for more]"
            )
        return section_text

    def _extract_item_block_from_markdown(
        self, text: str, canonical_item: str
    ) -> Optional[str]:
        """Extract an untruncated filing item or item subsection."""
        if not text:
            return None

        subsection_match = re.match(r"^Item\s+(\d+)\.([A-Z])$", canonical_item, re.I)
        if subsection_match:
            parent_item = f"Item {subsection_match.group(1)}"
            subsection_letter = subsection_match.group(2).upper()
            parent_text = self._extract_item_block_from_markdown(text, parent_item)
            if not parent_text:
                return None
            subsection_text = self._extract_lettered_subsection_from_markdown(
                parent_text, subsection_letter
            )
            return subsection_text or parent_text

        item_suffix = canonical_item.replace("Item ", "").strip()
        escaped_suffix = re.escape(item_suffix)
        # Match headings like:
        #   Item 5.
        #   ITEM 3.D
        #   ## Item 18 Financial Statements
        start_pattern = re.compile(
            rf"(?im)^(?:\s*#+\s*)?item\s+{escaped_suffix}(?:[\.\s:,-].*)?$"
        )
        next_item_pattern = re.compile(
            r"(?im)^(?:\s*#+\s*)?item\s+\d+[a-z]?(?:\.\d+|(?:\.[a-z]))?(?:[\.\s:,-].*)?$"
        )

        start_matches = list(start_pattern.finditer(text))
        if not start_matches:
            return None

        best_section = ""
        for start_match in start_matches:
            start = start_match.start()
            remainder = text[start_match.end():]
            end_match = next_item_pattern.search(remainder)
            end = start + end_match.start() if end_match else len(text)
            candidate = text[start:end].strip()
            if len(candidate) > len(best_section):
                best_section = candidate

        section_text = best_section.strip()
        return section_text or None

    @staticmethod
    def _extract_lettered_subsection_from_markdown(
        text: str, subsection_letter: str
    ) -> Optional[str]:
        """Extract a lettered subsection like D. within a 20-F item block."""
        start_pattern = re.compile(
            rf"(?im)^(?:\s*#+\s*)?{re.escape(subsection_letter)}\.\s*(?:.*)?$"
        )
        next_subsection_pattern = re.compile(
            r"(?im)^(?:\s*#+\s*)?[A-Z]\.\s*(?:.*)?$"
        )
        next_item_pattern = re.compile(
            r"(?im)^(?:\s*#+\s*)?item\s+\d+[a-z]?(?:\.\d+|(?:\.[a-z]))?(?:[\.\s:,-].*)?$"
        )

        start_matches = list(start_pattern.finditer(text))
        if not start_matches:
            return None

        best_section = ""
        for start_match in start_matches:
            start = start_match.start()
            remainder = text[start_match.end():]
            subsection_end_match = next_subsection_pattern.search(remainder)
            item_end_match = next_item_pattern.search(remainder)

            candidate_endings = []
            if subsection_end_match:
                candidate_endings.append(start + subsection_end_match.start())
            if item_end_match:
                candidate_endings.append(start + item_end_match.start())
            end = min(candidate_endings) if candidate_endings else len(text)

            candidate = text[start:end].strip()
            if len(candidate) > len(best_section):
                best_section = candidate

        return best_section or None

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

            actual_form = str(getattr(filing, "form", form_type)).upper()

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

            # 20-F path: use markdown extraction from the primary filing HTML
            # and slice by item headings instead of falling back to raw text.
            if actual_form == "20-F":
                markdown_text = self._get_filing_markdown_or_text(filing)
                if markdown_text:
                    extracted: Dict[str, str] = {}
                    resolved_20f = {
                        s: self._resolve_20f_section(s) for s in sections
                    }
                    for orig_name, canonical in resolved_20f.items():
                        section_text = self._extract_item_section_from_markdown(
                            markdown_text, canonical, max_chars_per_section
                        )
                        if section_text:
                            extracted[orig_name] = section_text

                    if extracted:
                        return {
                            "form": filing.form,
                            "date": str(filing.filing_date),
                            "url": filing.homepage_url or "",
                            "sections": extracted,
                            "available_items": sorted(self._SECTION_20F_LABELS.keys()),
                            "method": "markdown_sections",
                        }

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
        allowed_forms = (
            {form.upper() for form in form_types}
            if form_types else set(ANNUAL_FORM_TYPES) | set(QUARTERLY_FORM_TYPES)
        )

        form_kind = _form_filter_kind(form_types)
        if form_kind == "annual":
            allowed_fp = {"FY"}
        elif form_kind == "quarterly":
            allowed_fp = {"Q1", "Q2", "Q3", "Q4"}
        else:
            allowed_fp = None

        # Build concept fallback chain
        concepts_to_try = self._get_concepts_to_try(ticker, concept)

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
                exact_candidate = (
                    candidate if ":" in candidate else f"us-gaap:{candidate}"
                )
                # Use exact matching with us-gaap namespace to avoid
                # substring collisions (e.g. "StockholdersEquity" matching
                # "LiabilitiesAndStockholdersEquity").
                query = facts.query().by_concept(
                    exact_candidate, exact=True
                )

                # Apply form type filter via edgartools if single form
                if form_types and len(form_types) == 1:
                    query = query.by_form_type(form_types[0])

                df = query.to_dataframe()

                # Fallback to regex for non-US-GAAP filers (e.g. IFRS)
                if (df is None or df.empty):
                    query = facts.query().by_concept(candidate)
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

                # Duration-based filtering for period (non-instant) concepts.
                # 10-K XBRL includes quarterly comparison data alongside
                # annual totals, and 10-Q XBRL includes year-to-date
                # cumulative figures alongside single quarters.  Filter by
                # duration to get clean series.
                if ("period_start" in df.columns
                        and "period_end" in df.columns
                        and "period_type" in df.columns):
                    try:
                        import pandas as pd
                        # Only apply duration filter to non-instant concepts
                        is_duration = df["period_type"] == "duration"
                        if is_duration.any():
                            ps = pd.to_datetime(df["period_start"])
                            pe = pd.to_datetime(df["period_end"])
                            duration_days = (pe - ps).dt.days

                            if form_kind == "annual":
                                # Annual query: keep only full-year entries
                                # (≥300 days). Annual filings can embed
                                # quarterly comparison data (~90 days)
                                # tagged FY.
                                mask = ~is_duration | (duration_days >= 300)
                                df = df[mask]
                            elif form_kind == "quarterly":
                                # Quarterly query: keep only single-quarter
                                # entries (≤100 days).  10-Q XBRL embeds
                                # cumulative YTD data (180-270 days).
                                mask = ~is_duration | (duration_days <= 100)
                                df = df[mask]
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

        # Merge data from other alias concepts to fill period gaps.
        # Companies sometimes switch XBRL concepts between filings
        # (e.g. GOOGL switched from RevenueFromContract... to Revenues
        # in FY2025), leaving the "best" concept with missing years
        # that only exist under an older concept.
        if len(concepts_to_try) > 1 and "period_end" in df.columns:
            best_ends = set(df["period_end"].astype(str))
            for candidate in concepts_to_try:
                if candidate == best_candidate:
                    continue
                try:
                    exact_candidate = (
                        candidate if ":" in candidate else f"us-gaap:{candidate}"
                    )
                    query = facts.query().by_concept(
                        exact_candidate, exact=True
                    )
                    if form_types and len(form_types) == 1:
                        query = query.by_form_type(form_types[0])
                    alt_df = query.to_dataframe()
                    if alt_df is None or alt_df.empty:
                        continue
                    if "form_type" in alt_df.columns and (not form_types or len(form_types) > 1):
                        alt_df = alt_df[alt_df["form_type"].isin(allowed_forms)]
                    if allowed_fp and "fiscal_period" in alt_df.columns:
                        alt_df = alt_df[alt_df["fiscal_period"].isin(allowed_fp)]
                    if "unit" in alt_df.columns:
                        unit_map = {
                            "USD/shares": ["USD/shares", "USD per share"],
                            "shares": ["shares"],
                            "USD": ["USD"],
                        }
                        acceptable_units = unit_map.get(unit, [unit])
                        alt_df = alt_df[alt_df["unit"].isin(acceptable_units)]
                    if alt_df.empty:
                        continue
                    # Apply duration filter (same as main loop)
                    if ("period_start" in alt_df.columns
                            and "period_end" in alt_df.columns
                            and "period_type" in alt_df.columns):
                        try:
                            import pandas as pd
                            is_dur = alt_df["period_type"] == "duration"
                            if is_dur.any():
                                ps = pd.to_datetime(alt_df["period_start"])
                                pe = pd.to_datetime(alt_df["period_end"])
                                dur = (pe - ps).dt.days
                                if allowed_fp and allowed_fp == {"FY"}:
                                    alt_df = alt_df[~is_dur | (dur >= 300)]
                                elif allowed_fp and allowed_fp != {"FY"}:
                                    alt_df = alt_df[~is_dur | (dur <= 100)]
                        except Exception:
                            pass
                    if alt_df.empty:
                        continue
                    # Only keep rows for period_ends NOT already covered
                    alt_df = alt_df[~alt_df["period_end"].astype(str).isin(best_ends)]
                    if not alt_df.empty:
                        import pandas as pd
                        df = pd.concat([df, alt_df], ignore_index=True)
                except Exception:
                    continue

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

        # Build result dicts matching the API contract.
        # Derive FY from period_end rather than edgartools' fiscal_year,
        # which reflects the filing year (not the period year) for
        # comparative data embedded in later filings.
        def _fy_from_end(end_str: str) -> str:
            """Derive fiscal year label from period_end date."""
            if not end_str or len(end_str) < 10:
                return "?"
            year = int(end_str[:4])
            month_day = end_str[5:10]
            if month_day <= "01-10":
                year -= 1
            return f"FY{year}"

        results = []
        for _, row in df.iterrows():
            end_str = str(row.get("period_end", ""))
            results.append({
                "end": end_str,
                "val": row.get("numeric_value") if "numeric_value" in df.columns else row.get("value"),
                "form": row.get("form_type", ""),
                "fy": _fy_from_end(end_str),
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
        is_instant = _is_instantaneous(concept)

        if is_instant:
            rows = self.get_financial_metric(
                ticker, concept, taxonomy=taxonomy, unit=unit,
                periods=1,
                form_types=list(QUARTERLY_FORM_TYPES + ANNUAL_FORM_TYPES),
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
            periods=4, form_types=list(QUARTERLY_FORM_TYPES),
        )

        # Always fetch the most recent annual — needed for multiple checks
        annual = self.get_financial_metric(
            ticker, concept, taxonomy=taxonomy, unit=unit,
            periods=1, form_types=list(ANNUAL_FORM_TYPES),
        )

        if len(rows) < 4:
            # Fall back to annual
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

        ttm_end = rows[0]["end"]

        # If a more-recent annual (10-K) has been filed since the last 10-Q,
        # it contains Q4 data that our 10-Q sum can never include.  In that
        # case the annual IS the TTM and is strictly more current.
        if annual:
            annual_end = annual[0]["end"]
            annual_val = annual[0]["val"]
            # ISO-8601 strings compare correctly as plain strings
            if annual_end > ttm_end:
                return {
                    "ttm_val": annual_val,
                    "periods_used": 1,
                    "latest_quarter_end": annual_end,
                    "concept_used": annual[0].get("concept_used", concept),
                    "is_instantaneous": False,
                    "note": (
                        f"FY annual (10-K ending {annual_end}) is more current "
                        f"than 4Q TTM (ending {ttm_end}); Q4 now included."
                    ),
                }

            # Q4 gap fix: fiscal Q4 is reported in the 10-K, never as a
            # 10-Q.  When a 10-Q has been filed AFTER the annual period
            # end, the 4 most recent 10-Qs span ~15 months and skip Q4.
            # Detect this and derive Q4 = annual − sum(Q1+Q2+Q3).
            if (annual_val is not None
                    and rows[-1]["end"] < annual_end < rows[0]["end"]):
                in_annual = [r for r in rows if r["end"] <= annual_end]
                after_annual = [r for r in rows if r["end"] > annual_end]

                if len(in_annual) == 3 and len(after_annual) == 1:
                    q123_sum = sum(
                        r["val"] for r in in_annual
                        if r.get("val") is not None
                    )
                    q4_val = annual_val - q123_sum
                    # TTM = post-annual quarter + derived Q4 + 2 most
                    # recent pre-annual quarters
                    ttm_quarters = (
                        after_annual
                        + [{"end": annual_end, "val": q4_val,
                            "derived": True}]
                        + in_annual[:2]
                    )
                    ttm_val = sum(
                        r["val"] for r in ttm_quarters
                        if r.get("val") is not None
                    )
                    return {
                        "ttm_val": ttm_val,
                        "periods_used": 4,
                        "latest_quarter_end": ttm_end,
                        "quarters": [
                            {"end": r["end"], "val": r["val"],
                             **({"derived": True} if r.get("derived") else {})}
                            for r in ttm_quarters
                        ],
                        "concept_used": rows[0].get("concept_used", concept),
                        "is_instantaneous": False,
                        "note": (
                            f"Q4 (ending {annual_end}) derived from annual "
                            f"minus Q1+Q2+Q3."
                        ),
                    }

        ttm_val = sum(r["val"] for r in rows if r.get("val") is not None)
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

    # ── Per-share historical fundamentals ────────────────────────────────

    def get_per_share_fundamentals(
        self,
        ticker: str,
        periods: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute historical per-share fundamentals from SEC XBRL data.

        Returns annual series for:
          - Diluted shares outstanding (weighted average)
          - Book value per share (Equity / Diluted Shares)
          - Tangible book value per share ((Equity - Goodwill - Intangibles) / Diluted Shares)
          - Revenue per share
          - Operating cash flow per share
          - Diluted EPS
          - Total revenue ($)
          - Operating cash flow ($)

        All values are from annual filings (10-K / 20-F / 40-F).
        """
        company = self._get_company(ticker)
        if not company:
            return None

        # Fetch all needed metrics in annual filing series.
        # Over-fetch because annual XBRL filings can include quarterly comparison
        # data that eats period slots; _by_year deduplicates to annual.
        fetch_periods = periods * 4

        def _fetch(concept: str, unit: str = "USD") -> List[Dict[str, Any]]:
            return self.get_financial_metric(
                ticker, concept, unit=unit,
                periods=fetch_periods, form_types=list(ANNUAL_FORM_TYPES),
            )

        shares_metric = "WeightedAverageNumberOfDilutedSharesOutstanding"
        shares_data = _fetch(shares_metric, unit="shares")
        if not shares_data:
            logger.info(
                f"{ticker}: no share series from companyfacts for "
                f"{shares_metric}; trying latest annual filing concept discovery"
            )
            discovered_share_concept = (
                self._discover_weighted_share_concept_from_latest_annual_filing(ticker)
            )
            if discovered_share_concept:
                logger.info(
                    f"{ticker}: retrying companyfacts share query with discovered concept "
                    f"{discovered_share_concept}"
                )
                shares_data = _fetch(shares_metric, unit="shares")
            else:
                logger.info(
                    f"{ticker}: latest annual filing concept discovery found no share concept"
                )
        equity_data = _fetch("StockholdersEquity")
        goodwill_data = _fetch("Goodwill")
        intangibles_data = _fetch("IntangibleAssetsNetExcludingGoodwill")
        revenue_data = _fetch("Revenues")
        opcf_data = _fetch("NetCashProvidedByUsedInOperatingActivities")
        net_income_data = _fetch("NetIncomeLoss")

        # For revenue and EPS, the ASC 606 transition (~2018) means the
        # modern concept only has data from ~2019 forward.  Fetch the
        # legacy concepts and merge so we get full 10-year coverage.
        for legacy_concept in ["SalesRevenueNet", "SalesRevenueGoodsNet"]:
            legacy = self.get_financial_metric(
                ticker, legacy_concept, unit="USD",
                periods=periods, form_types=list(ANNUAL_FORM_TYPES),
            )
            if legacy:
                revenue_data = revenue_data + legacy
                break  # one legacy source is enough

        if not shares_data and not net_income_data and not revenue_data:
            return None

        # Index each metric by fiscal year (period_end year).
        # Data arrives sorted by period_end DESC.  For each year keep
        # only the LARGEST value — this picks the annual total over any
        # quarterly entries that leak through 10-K XBRL comparative data.
        def _fiscal_year(end: str) -> int:
            """Map period_end date to fiscal year.

            Companies with 52/53-week fiscal calendars (e.g. JNJ, COST)
            sometimes have period_end in early January (e.g. 2021-01-03
            for FY2020).  If the date is in the first 10 days of January
            we assign it to the prior calendar year.
            """
            year = int(end[:4])
            month_day = end[5:10]  # "MM-DD"
            if month_day <= "01-10":
                year -= 1
            return year

        def _by_year(data: List[Dict]) -> Dict[int, float]:
            result: Dict[int, float] = {}
            for row in data:
                end = row.get("end", "")
                val = row.get("val")
                if end and val is not None:
                    year = _fiscal_year(end)
                    if year not in result or abs(val) > abs(result[year]):
                        result[year] = val
            return result

        shares_by_year = _by_year(shares_data)
        equity_by_year = _by_year(equity_data)
        goodwill_by_year = _by_year(goodwill_data)
        intangibles_by_year = _by_year(intangibles_data)
        revenue_by_year = _by_year(revenue_data)
        opcf_by_year = _by_year(opcf_data)
        net_income_by_year = _by_year(net_income_data)

        # ── Split adjustment ─────────────────────────────────────────
        # XBRL comparative data is inconsistent across filings: some
        # years are already retroactively split-adjusted by later 10-Ks
        # and some are not.  Rather than relying on yfinance split dates
        # (which can double-count), detect splits directly from share
        # count discontinuities.  Walk from newest year backward; if
        # shares jump by ~2x/3x/4x/5x/7x/10x between adjacent years,
        # apply that factor to the older year and all preceding years.
        KNOWN_RATIOS = [2, 3, 4, 5, 6, 7, 8, 10, 15, 20]
        sorted_years = sorted(shares_by_year.keys(), reverse=True)
        cumulative_factor = 1.0
        split_factors: Dict[int, float] = {}

        for i in range(len(sorted_years) - 1):
            newer_yr = sorted_years[i]
            older_yr = sorted_years[i + 1]
            newer_shares = shares_by_year[newer_yr]
            older_shares = shares_by_year[older_yr]

            if older_shares and newer_shares and older_shares != 0:
                ratio = newer_shares / older_shares
                # Check if ratio is close to a known split factor
                for known in KNOWN_RATIOS:
                    if 0.85 * known <= ratio <= 1.15 * known:
                        cumulative_factor *= known
                        break

            split_factors[older_yr] = cumulative_factor

        # Apply split adjustments to shares for older years
        for yr, factor in split_factors.items():
            if factor != 1.0:
                if yr in shares_by_year:
                    shares_by_year[yr] *= factor

        # Collect all years that have at least shares or revenue
        all_years = sorted(
            set(shares_by_year) | set(net_income_by_year) | set(revenue_by_year),
            reverse=True,
        )[:periods]

        rows = []
        for year in all_years:
            shares = shares_by_year.get(year)
            equity = equity_by_year.get(year)
            goodwill = goodwill_by_year.get(year, 0)
            intangibles = intangibles_by_year.get(year, 0)
            revenue = revenue_by_year.get(year)
            opcf = opcf_by_year.get(year)
            net_income = net_income_by_year.get(year)

            row: Dict[str, Any] = {"year": year}

            # Diluted shares (millions)
            if shares is not None:
                row["diluted_shares"] = shares
                row["diluted_shares_m"] = shares / 1_000_000
            else:
                row["diluted_shares"] = None
                row["diluted_shares_m"] = None

            # Book value per share
            if equity is not None and shares:
                row["book_value_per_share"] = equity / shares
            else:
                row["book_value_per_share"] = None

            # Tangible book value per share
            if equity is not None and shares:
                tangible_equity = equity - (goodwill or 0) - (intangibles or 0)
                row["tangible_bv_per_share"] = tangible_equity / shares
            else:
                row["tangible_bv_per_share"] = None

            # Revenue per share
            if revenue is not None and shares:
                row["revenue_per_share"] = revenue / shares
            else:
                row["revenue_per_share"] = None

            # Operating cash flow per share
            if opcf is not None and shares:
                row["opcf_per_share"] = opcf / shares
            else:
                row["opcf_per_share"] = None

            # Diluted EPS (computed from net income / split-adjusted shares)
            if net_income is not None and shares:
                row["eps_diluted"] = net_income / shares
            else:
                row["eps_diluted"] = None

            # Absolute values
            row["total_revenue"] = revenue
            row["net_income"] = net_income
            row["operating_cash_flow"] = opcf

            rows.append(row)

        # Track which concepts were actually used for transparency
        concepts_used = {}
        if shares_data:
            shares_concept = shares_data[0].get("concept_used", "")
            concepts_used["diluted_shares"] = shares_concept
            if shares_concept and shares_concept != shares_metric:
                lower_concept = shares_concept.lower()
                if "basic" in lower_concept and "diluted" not in lower_concept:
                    concepts_used["shares_note"] = (
                        "Used basic weighted-average shares because no diluted share concept was available."
                    )
        if equity_data:
            concepts_used["equity"] = equity_data[0].get("concept_used", "")
        if goodwill_data:
            concepts_used["goodwill"] = goodwill_data[0].get("concept_used", "")
        if intangibles_data:
            concepts_used["intangibles"] = intangibles_data[0].get("concept_used", "")
        if revenue_data:
            concepts_used["revenue"] = revenue_data[0].get("concept_used", "")
        if opcf_data:
            concepts_used["operating_cf"] = opcf_data[0].get("concept_used", "")
        if net_income_data:
            concepts_used["net_income"] = net_income_data[0].get("concept_used", "")

        # Note any years that were split-adjusted
        adjusted_years = [
            yr for yr, f in split_factors.items() if f != 1.0
        ]

        return {
            "ticker": ticker.upper(),
            "entity_name": getattr(company, "name", ticker),
            "periods": len(rows),
            "rows": rows,
            "concepts_used": concepts_used,
            "split_adjusted": bool(adjusted_years),
            "split_adjusted_years": sorted(adjusted_years),
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
                form_filter = list(QUARTERLY_FORM_TYPES)
            else:
                form_filter = list(ANNUAL_FORM_TYPES)

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

            # Grab quick metrics — use get_financial_metrics() for the
            # full set, then patch any Nones with CF DataFrame fallback.
            try:
                base = financials.get_financial_metrics()

                # edgartools' get_operating_cash_flow() returns None for
                # some companies (e.g. AAPL) when the CF label doesn't
                # match its expected pattern.  Fall back to reading the
                # CF DataFrame for the standard_concept we know works.
                ocf = base.get("operating_cash_flow")
                capex = base.get("capital_expenditures")
                fcf = base.get("free_cash_flow")

                if ocf is None or fcf is None:
                    cf_stmt = result.get("cashflow_statement")
                    if cf_stmt:
                        cf_rows = cf_stmt.get("rows", [])
                        cf_periods = cf_stmt.get("periods", [])
                        latest_period = cf_periods[0] if cf_periods else None
                        if latest_period:
                            for r in cf_rows:
                                concept = r.get("concept", "")
                                std = r.get("standard_concept", "")
                                if (ocf is None
                                        and "NetCashProvidedByUsedInOperatingActivities"
                                        in concept
                                        and "Abstract" not in concept):
                                    val = r.get(latest_period)
                                    if val is not None and not (isinstance(val, float) and val != val):
                                        ocf = val
                                        break

                    if ocf is not None and fcf is None and capex is not None:
                        fcf = ocf - abs(capex)

                result["quick_metrics"] = {
                    "revenue": base.get("revenue"),
                    "net_income": base.get("net_income"),
                    "operating_income": base.get("operating_income"),
                    "total_assets": base.get("total_assets"),
                    "total_liabilities": base.get("total_liabilities"),
                    "stockholders_equity": base.get("stockholders_equity"),
                    "operating_cash_flow": ocf,
                    "free_cash_flow": fcf,
                    "capital_expenditures": capex,
                    # New metrics from get_financial_metrics()
                    "current_assets": base.get("current_assets"),
                    "current_liabilities": base.get("current_liabilities"),
                    "current_ratio": base.get("current_ratio"),
                    "debt_to_assets": base.get("debt_to_assets"),
                    "shares_outstanding_basic": base.get("shares_outstanding_basic"),
                    "shares_outstanding_diluted": base.get("shares_outstanding_diluted"),
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

        Fetches all insider form types and interleaves them by filing date
        (newest first) so Form 3 and Form 5 filings aren't crowded out by
        the typically larger volume of Form 4 filings.
        """
        company = self._get_company(ticker)
        if not company:
            return []

        # Collect raw filings from all insider form types, interleaved
        # by date.  Fetch a generous window then sort + trim.
        raw_filings = []
        try:
            try:
                filings = company.get_filings(form=["3", "4", "5"])
                for f in filings:
                    raw_filings.append(f)
                    if len(raw_filings) >= max_results * 2:
                        break
            except Exception:
                # Fallback: fetch each type individually
                for form_type in ["4", "3", "5"]:
                    try:
                        filings = company.get_filings(form=form_type)
                        for f in filings:
                            raw_filings.append(f)
                            if len(raw_filings) >= max_results * 2:
                                break
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to get insider filings for {ticker}: {e}")
            return []

        # Sort by filing date descending
        raw_filings.sort(
            key=lambda f: str(getattr(f, "filing_date", "")), reverse=True
        )

        results = []
        for f in raw_filings[:max_results]:
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

        return results
