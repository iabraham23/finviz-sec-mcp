# Finviz + SEC EDGAR MCP Server

A **free** MCP server for stock research using Finviz screening and SEC EDGAR filings. No paid subscriptions required.

Works with any MCP-compatible client: Claude Desktop, Claude Code, Cursor, Windsurf, Cline, Zed, and more.

https://financial-research-finviz-sec-mcp.onrender.com/mcp 

## Collaboration Preference

This project is released under the MIT license. If you build on it, I would highly prefer and appreciate active collaboration.

This is a request about how I would like collaboration to happen, not an additional license restriction.

## What You Get

**21 tools** accessible conversationally through any MCP client:

| Tool | What it does |
|------|-------------|
| `screen_stocks` | Full Finviz screener with 67+ filters: P/E, ROE, margins, debt ratios, etc. |
| `screen_value_stocks` | Quick value screen with sensible defaults |
| `screen_from_url` | Paste any finviz.com screener URL and run it |
| `list_filter_options` | Discover all available filter codes |
| `get_stock_fundamentals` | 90+ data points for any ticker |
| `compare_stocks` | Side-by-side fundamental comparison |
| `get_sec_filings` | List recent SEC filings (10-K, 10-Q, 8-K, etc.) |
| `get_filing_text` | Read clean text of SEC filings (iXBRL properly stripped) |
| `get_financial_history` | Historical revenue, net income, EPS from XBRL data |
| `get_financial_snapshot` | Full income statement, balance sheet & cash flow from latest filing |
| `get_financial_ttm` | Trailing twelve months for one or more companies |
| `compare_financials` | Compare a metric across multiple companies for a given year |
| `get_insider_filings` | SEC Form 3/4/5 insider filings with structured trade data |
| `compare_sectors` | Sector-level comparison |
| `compare_industries` | Industry aggregate comparison |
| `stock_vs_industry` | Compare one stock against its industry aggregates |
| `screen_industry` | Filter within a specific industry |
| `get_analyst_ratings` | Analyst price targets and ratings |
| `get_insider_activity` | Insider buy/sell activity |
| `get_stock_news` | Recent news headlines |
| `get_earnings_news` | Earnings-related and transcript-related headlines |

## Data Sources

- **Finviz** (free tier): Screener, fundamentals, news, insiders, analyst data. Delayed 15–20 min (irrelevant for value research).
- **SEC EDGAR** (free, public): 10-K/10-Q/8-K filings, XBRL financial data, insider forms. No API key needed.

---

## Setup Guide (macOS / Linux / Windows)

### Step 1: Prerequisites

You need **Python 3.10+** and **pip**. Check with:

```bash
python3 --version   # Should be 3.10 or higher
pip3 --version
```

If you don't have Python 3.10+, install it from [python.org](https://www.python.org/downloads/).

### Step 2: Fork, Clone & Install

Preferred workflow: fork this repository on GitHub first, then clone your fork so improvements can flow back cleanly.

```bash
git clone https://github.com/YOUR_USERNAME/finviz-sec-mcp.git
cd finviz-sec-mcp

# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate          # Windows

# Install the package
pip install -e .
```

For the remote server entrypoint, the package also installs:

```bash
finviz-sec-mcp-remote
```

### Step 3: Configure Environment

Copy the example env file and add your email (required by the SEC for EDGAR API access):

```bash
cp .env.example .env
```

Edit `.env` and set your contact email:

```
SEC_EMAIL=your-email@example.com
```

### Step 4: Test It Works

```bash
# Quick test — should print the current tool count
python -c "
from finviz_sec_mcp.server import server
print(f'{len(server._tool_manager._tools)} tools registered')
"

# Full test — runs a live value screen
python -c "
from finviz_sec_mcp.clients.finviz_client import FinvizClient
results = FinvizClient.screen(
    filters=['cap_largeover', 'fa_pe_u20', 'fa_roe_o15'],
    table='Valuation',
)
print(f'Found {len(results)} value stocks')
for s in results[:3]:
    print(f'  {s[\"Ticker\"]} — P/E: {s.get(\"P/E\")}')
"
```

### Step 5: Configure Claude Desktop

Open your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Add the following (replace `/path/to/` with your actual path):

```json
{
  "mcpServers": {
    "finviz-sec": {
      "command": "/path/to/finviz-sec-mcp/venv/bin/finviz-sec-mcp"
    }
  }
}
```

**Finding your actual path:**

```bash
# Run this in the project folder to get the exact paths
echo "\"command\": \"$(pwd)/venv/bin/finviz-sec-mcp\""
```

### Step 6: Restart Claude Desktop

Quit and reopen Claude Desktop. You should see a hammer icon (🔨) in the
chat input area. Click it to see all 21 tools.

---

## Remote Server Deployment

This repo can also run as a public remote MCP over FastMCP streamable HTTP. That is the preferred setup for org-wide use because the production service can deploy from GitHub `main` and users no longer need `.mcpb` uploads.

### Remote Environment

Set the remote variables from [`.env.example`](/Users/ishanabraham/CWC_Work/finviz-sec-mcp/.env.example):

```bash
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_STREAMABLE_HTTP_PATH=/mcp
SEC_EMAIL=your-email@example.com
```

### Local Remote Run

```bash
finviz-sec-mcp-remote
```

This exposes:

- `/mcp`
- `/healthz`

### Render Deployment

This repo includes a starter [render.yaml](/Users/ishanabraham/CWC_Work/finviz-sec-mcp/render.yaml) that:

- deploys the web service from GitHub
- runs `finviz-sec-mcp-remote`
- health-checks `/healthz`

To keep production tied to GitHub `main`, configure the Render production service to deploy only from the `main` branch. Unpushed local changes will not affect the live server.

This public remote deployment does not require OAuth or a backing database. Anyone with the deployed `/mcp` URL can connect, so put rate limiting or basic WAF rules in front of it if you expect outside traffic.

---

## Screener Table Views

The `screen_stocks` tool accepts a `table` parameter that controls which columns are returned. Each view shows different metrics:

| View | Columns Returned |
|------|-----------------|
| **Overview** | Company, Sector, Industry, Market Cap, P/E, Price, Change, Volume |
| **Valuation** | Market Cap, P/E, Fwd P/E, PEG, P/S, P/B, P/C, P/FCF, EPS This Y, EPS Next Y, EPS Past 5Y, EPS Next 5Y, Sales Past 5Y, Price, Change, Volume |
| **Financial** | Market Cap, Dividend, ROA, ROE, ROI, Current Ratio, Quick Ratio, LTDebt/Eq, Debt/Eq, Gross Margin, Oper Margin, Profit Margin, Earnings, Price, Change, Volume |
| **Ownership** | Market Cap, Outstanding, Float, Insider Own, Insider Trans, Inst Own, Inst Trans, Float Short, Short Ratio, Avg Volume, Price, Change, Volume |
| **Performance** | Perf Week, Perf Month, Perf Quart, Perf Half, Perf Year, Perf YTD, Volatility W, Volatility M, Recom, Avg Volume, Rel Volume, Price, Change, Volume |
| **Technical** | Beta, ATR, SMA20, SMA50, SMA200, 52W High, 52W Low, RSI, Price, Change, Volume |

Default is **Valuation**. You can run the same screen with different views to get a fuller picture of the results.

---

## Example Prompts

Once set up, you can just talk naturally:

> "Find me undervalued large-cap stocks with strong margins and low debt"

> "Compare AAPL, MSFT, and GOOGL on valuation and profitability metrics"

> "Show me the most recent 10-K filing for Berkshire Hathaway"

> "What's the historical revenue trend for NVDA from SEC filings?"

> "Screen for dividend stocks with yield over 3%, payout under 60%, and ROE over 15%"

> "Show me all consumer defensive stocks with P/E under 20"

> "What are the latest insider trades for AAPL?"

> "Get analyst price targets for META"

---

## Troubleshooting

**"No module named 'finviz'"** → Make sure you activated the venv and ran `pip install -e .`

**`No module named 'src'` or stale `value-investor-mcp` paths** → You renamed the project but are still using an old editable install or old Claude config. Recreate the venv, reinstall with `pip install -e .`, and point Claude Desktop at `venv/bin/finviz-sec-mcp`.

**Screener returns empty** → Some filter combinations are too restrictive. Try `list_filter_options` to check valid codes.

**SEC EDGAR rate limit** → The client auto-throttles to 10 req/sec. If you hit issues, wait a few seconds.

**Claude Desktop doesn't show the tools** → Double-check the path in `claude_desktop_config.json`. The `command` should point to `venv/bin/finviz-sec-mcp` inside this project, not your system Python.

## License

MIT. See [LICENSE](/Users/ishanabraham/CWC_Work/finviz-sec-mcp/LICENSE).
