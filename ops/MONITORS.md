# Feeds & monitors (OOTL)

Agent decision inputs. Scans are marketwide; **always intersect** with `watchlists/nick_themes.txt` before trading.

## Robinhood Legend scans (live)

| Feed | Scan ID | Use |
|------|---------|-----|
| ORB book (3–10% gap, rvol≥2, $10+, 1M adv) | `1011ea56-1b5c-4791-a5ed-c5a03ad2d19e` | **Primary** — Setup 1 ORB / Setup 2 VWAP |
| ≤$15 gainers + rvol≥1.5 | `64edeeda-2d43-434f-a772-2cee4c578b7d` | Secondary; intersect themes + quality filters |
| ≤$15 losers + rvol≥1.5 | `b3dd8e13-9019-4ee7-89ee-1a72f7d28010` | Avoid chase / optional fade later |
| ≤$15 gap ≥3% | `c26e0522-6f57-44d1-aa11-d2520cc0dd7e` | Premarket / open gap list |
| Probe daily gainers (temp) | `50d42a47-f56e-4567-b938-7917957db996` | Delete when convenient |

Re-run via `run_scan` with `scan_id`.

## Local files

| Path | Role |
|------|------|
| `watchlists/nick_themes.txt` | Hard universe |
| `watchlists/orb_alist.txt` | Liquid theme names for ORB/VWAP ($10+) |
| `ops/OOTL_STRATEGY.md` | Risk + setups + authority |
| `ops/decision_log.md` | Append each decision / trade |

## MCP tools (per tick)

1. **Macro:** `get_index_quotes` / `get_equity_quotes` on SPY, QQQ, IWM  
2. **Scan:** `run_scan` on **ORB book** first, then gap/gainer scans → intersect `nick_themes.txt` + `orb_alist.txt`
3. **Catalyst / chatter:** Finviz `get_stock_news`; **`screen_asia_social_chatter`** (6:00 AM); `get_stocktwits_trending` (theme_only)
4. **Levels:** 5m ORB high/low; minute VWAP via `get_equity_technical_indicators` type=vwap; SPY/QQQ for Setup 3
5. **Account:** `get_portfolio` / `get_accounts` — confirm agentic + BP before order  
6. **Trade:** `review_equity_order` → (OOTL) `place_equity_order`

## Cadence (ET)

| Window | Interval | Job |
|--------|----------|-----|
| 08:00–09:25 | every 10m | Premarket: gap scan + news on theme hits; draft ≤2 plans |
| 09:30–09:40 | once | **No entries** — let 5m ORB form |
| 09:40–11:30 | every 5m | Setups 1–5 only; manage position |
| 11:30–15:30 | every 15m | Manage only if in a trade; no new entries |
| 15:30–15:45 | every 5m | Flatten if still open |
| After 15:45 | stop | Journal to `decision_log.md` |

## Runtime requirement

OOTL **live trading** needs this Agents session (or equivalent) open with Robinhood + Finviz MCP connected. Cloud Automations cannot use local `finviz-sec` unless those servers are also on the Cursor dashboard.

## Kill switch

User: `stop OOTL` / `flatten now` → cancel working orders, flatten equity, disarm loops, set HITL-only.
