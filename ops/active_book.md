# Active book — stocks under analysis

**Updated:** 2026-08-24 premarket  
**Source:** `watchlists/analysis_universe.txt` (151 tickers) via `scan_analysis_universe`  
**Rule:** Only names on this page get levels, plans, or orders. Marketwide RH scans are cross-check only.

---

## How this file works

1. Run `scan_analysis_universe` on the full book.
2. Promote movers (|change| ≥ 1%, liquid, on-theme) into **Active** below.
3. Fill catalyst + location before any trade idea.
4. Demote to **Watching** when quiet; drop when off-theme or account-killer.

---

## Active (work these)

### BABA — −8.6% | $119 | vol 32M
| Field | Value |
|-------|-------|
| **Catalyst** | HK$80B placing (~$10B) to fund AI; shares −8% on dilution fear. Burry exited, called pricey. |
| **Theme** | Cloud/AI + Asia ADR |
| **Location** | Gap down on dilution headline — not ORB long until structure; watch PMH hold/fail |
| **PMH / PML / VWAP** | *fill at open* |
| **Extension** | SMA20 TBD |
| **Float / adv** | Mega-cap ADR, liquid |
| **Headwind** | Dilution + Burry skepticism; Asia sentiment |
| **Setup** | None pre-open — wait for 09:40+ structure (reclaim VWAP or failed bounce short only if rules fit) |
| **Status** | **Analyzing** — catalyst clear, levels pending |

### FSLY — +9.9% | $25 | vol 5.6M
| Field | Value |
|-------|-------|
| **Catalyst** | Strong move; last news Q2 earnings (Aug 6) — verify if fresh headline or sympathy |
| **Theme** | Cloud/edge CDN |
| **Location** | Extended off earnings base — check SMA extension before long |
| **PMH / PML / VWAP** | *fill at open* |
| **Setup** | ORB only if gap holds structure + rvol; else pass |
| **Status** | **Analyzing** — confirm today's driver |

### MP — +9.1% | $60 | vol 8.4M
| Field | Value |
|-------|-------|
| **Catalyst** | Rare earth / defense supply chain; +9% move — pull headline |
| **Theme** | Defense / materials (in universe) |
| **Location** | +19% above SMA20 — extension flag |
| **Float / adv** | Adv ~6M, rel vol 1.4× |
| **Setup** | Likely **pass** on long unless pullback to VWAP — extended |
| **Status** | **Watching** — extended, need catalyst confirm |

### FUTU — +9.7% | $124 | vol 3.5M
| Field | Value |
|-------|-------|
| **Catalyst** | Asia broker ADR — often tracks HK/China sentiment; check vs BABA |
| **Theme** | Asia ADR |
| **Status** | **Analyzing** — correlate with BABA/Asia tape |

### MRVL — −5.6% | $237 | vol 25M
| Field | Value |
|-------|-------|
| **Catalyst** | Semi weakness / peer sympathy |
| **Theme** | AI infra |
| **Status** | **Watching** — liquid, need level map if promoting |

---

## Watching (book movers, not primary focus)

PSN +6.5% | TSLA +5.1% | NET +5.1% | SOUN +5.0% | UPST +5.0% | BBAI +4.9% | RXRX +4.8% | BEKE +4.5% | ONDS +3.9% | ZS +3.9% | SMR +3.6% | SNOW +3.6% | PLTR +3.4% | ORCL +3.1% | PATH +3.0%

---

## Not in book (ignore)

Anything from RH marketwide scans that is **not** in `analysis_universe.txt` — e.g. low-float biotech, crypto proxies, random gappers.
