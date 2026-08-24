# Social feeds — Asia headlines & chatter

Morning pipeline for **Asia session → US ADR gap** context. Intersect results with `nick_themes.txt` before trading.

## What works today (no extra keys)

| Source | MCP tool | Notes |
|--------|----------|--------|
| **Stocktwits trending** | `get_stocktwits_trending` | Public API; `theme_only=true` filters to your book |
| **Stocktwits per-ticker** | `get_stocktwits_stream` | Recent messages + Bullish/Bearish tags |
| **Asia ADR screen** | `screen_asia_social_chatter` | Combines Stocktwits + Finviz headlines; ranks headwinds |
| **Finviz news** | `get_stock_news` | Already in MCP |

**6:00 AM routine:** `screen_asia_social_chatter` → if PDD/BABA/TSM flag headwinds, tighten stops or skip longs.

Watchlist: `watchlists/asia_adr.txt` (BABA, BIDU, TSM, PDD, XPEV, …).

## Optional: Grok (xAI)

| Env | `finviz-sec-mcp/.env` |
|-----|------------------------|
| `XAI_API_KEY` | From [console.x.ai](https://console.x.ai/) |
| `XAI_MODEL` | Optional; default `grok-3-latest` |

Tool: `query_grok_market_chatter` — macro narrative cross-check only, not auto-trade signal.

## Not wired yet — what it takes

### X (Twitter) — wired

| Env | `X_BEARER_TOKEN` in `finviz-sec-mcp/.env` |
| Tools | `search_x_posts`, `search_x_asia_headlines` |

Read-only recent search (~7 days). Restart finviz-sec MCP after adding the token.

### X (Twitter) — not needed if using hosted MCP

### Truth Social

- **No official public API** for search/trends.
- Options: manual watch, third-party scrapers (fragile, ToS risk), or skip.
- Not recommended for automated trading signals until a stable API exists.

### Grok via X app

- Different from xAI API — tied to X subscription. Use **xAI API** path above for agent access.

## Restart after changes

1. Edit `C:\Users\nickr\Documents\Open_Models\finviz-sec-mcp\.env` (keys only — never commit).
2. **Cursor → Settings → MCP** — restart **finviz-sec** server (or reload window).
3. Smoke: `screen_asia_social_chatter` in agent chat.

## Agent rule

Social chatter **narrows the watchlist** and flags **headwinds** — it does not override OOTL risk rules or replace ORB/VWAP structure.
