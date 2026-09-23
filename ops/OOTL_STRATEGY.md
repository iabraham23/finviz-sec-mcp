# OOTL Theme Daytrade — $500

Nick is out of the loop. Agent runs the process end-to-end within these hard limits.

**Philosophy:** boring, repeatable, risk-defined. Same handful of patterns until execution is automatic. No chasing 150% low-float runners.

## Authority

- **Universe:** only tickers in `watchlists/nick_themes.txt` (AI + Cloud + Defense).
- **Capital:** $500 agentic Robinhood account (never exceed available BP).
- **Live trades:** allowed **without** per-trade confirmation while OOTL is active.
- **Revoke:** user says “stop OOTL” / “flatten” / “HITL only” → cancel opens, flatten, no new entries.

## Hard risk

| Rule | Value |
|------|--------|
| Max open positions | 1 |
| Risk per trade | **$2.50–$5** (0.5–1% of $500); hard cap **$25** on normal setups |
| Failed-parabolic short | **half risk** ($1.25–$2.50); cover fast on squeeze signs |
| Notional per entry | $200–350 (fractionals OK in RTH) |
| Cash reserve | ≥ $150 until trade is working |
| Entries | **09:40–11:30 ET** (after 5m ORB can form; no first-spike entries) |
| Flat by | 15:45 ET |
| Overnight | never |
| After a full stop | done for the day |
| Adds | winners only — never average down |
| Target default | **2R–3R** or key level (PMH, prior day high, measured move) |

Size: `shares = risk_dollars / (entry - stop)`, cap notional at $350.

## Stock quality (before any setup)

Must pass **all** unless noted:

| Filter | Rule |
|--------|------|
| Theme | In `nick_themes.txt` |
| Catalyst | Earnings, news, sector move — Finviz `get_stock_news` |
| Price | **≥ $10** (ideal $20+ for ORB); sub-$10 only on **Setup 4** parabolic short with half size |
| Avg volume | **≥ 1M** shares (30d) |
| Relative volume | **≥ 2×** normal |
| Gap / change | **+3% to +10%** preferred — **reject if already +50%** (parabolic chase) |
| Float | Know it (Finviz fundamentals) — avoid unknown pump structure |

Prefer intersection with `watchlists/orb_alist.txt` for liquid ORB/VWAP names.

## Setups (only these five)

Trade **one** pattern per day. Two max plans written; **one** execution.

### 1. Opening Range Breakout (ORB) — primary

**What:** Mark first **5m** range (sometimes 15m). Long on clean break of range **high** with volume. Short on break of range **low** only if Setup 4 rules also met.

**Entry:** Clean break + volume confirmation — not the first violent 9:30 spike.  
**Stop:** Below range low (long) or above range high (short).  
**Target:** 2R–3R, VWAP extension, prior day high, measured move.

**Timing:** Range complete ~**09:35–09:40**; entries from **09:40**.

### 2. VWAP reclaim (gap continuation)

**What:** Gapped **+3% to +10%** on catalyst. Pulls to VWAP, holds, **1m or 5m close back above VWAP** with volume → long.

**Stop:** Below pullback low (below VWAP failure).  
**Target:** PMH, opening high, 2R–3R.

**Reject:** Gap +80%, sympathy with no catalyst, SPY risk-off day without RS (Setup 3).

### 3. Relative strength vs SPY/QQQ

**What:** SPY/QQQ weak; theme name holds gains / higher lows above VWAP or key level. Enter on SPY bottoming sign **or** stock breaks short consolidation.

**Stop:** Below consolidation low.  
**Target:** Morning high, measured move.

**Always:** SPY or QQQ on bias check every tick.

### 4. Failed parabolic short — **only short allowed**

**What:** Low-float already **+80% to +200%** on day, multiple spikes, clear **lower high**, loses VWAP/support on **volume** → short the breakdown, never into strength.

**Stop:** Above lower high / recent swing high.  
**Size:** **Half** normal risk. Cover immediately on squeeze/halt risk.

**Not** “it can’t go higher.” Need breakdown confirmation.

### 5. Earnings gap — structure first

**What:** Earnings gap. **Do not** trade first 5–15 min chaos. Wait for first **5m range**. Long: holds VWAP + breaks opening high. Short: loses VWAP + breaks opening low (Setup 4 sizing if parabolic).

**Stop:** Other side of range.  
**Target:** Measured move / key level.

## Account killers (hard no)

| # | Killer | Rule |
|---|--------|------|
| 1 | Chase low-float gappers after 10 min | No violent green spike buys. Miss it or wait for base/retest. |
| 2 | Short parabolic without breakdown | Only Setup 4, half size |
| 3 | Average down | One entry; add winners only |
| 4 | Midday scalping | No new entries after **11:30** |
| 5 | Fade “overextended” | No RSI/SMA fade; price confirmation only |
| 6 | Pump without float + catalyst | No trade |
| 7 | Earnings gap without structure | Setup 5 only — wait for range |

### Low-float gapper profile → default **skip**

Unless Setup 4 short with half size after confirmed top. Random scan hits **not in themes** → ignore.

## Expected edge (discipline > win rate)

Example math Nick uses: 50% win rate, avg win **2R**, avg loss **0.7R** → +65R over 100 trades.  
Requires: defined risk before entry, cut losers, let winners work, **no boredom/FOMO trades**.

## Order prefs (Robinhood agentic)

- RTH for entries; `$` market fractionals OK when stop math fits.
- `review_equity_order` → `place_equity_order`; stop plan immediate.
- `get_equity_tradability` before fractional sizing.
