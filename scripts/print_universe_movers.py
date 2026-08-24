"""One-off: print analysis universe movers."""
from finviz_sec_mcp.tools.universe_monitor import _load_universe
import yfinance as yf

tickers = _load_universe()
raw = yf.download(tickers, period="5d", group_by="ticker", threads=True, progress=False)
rows = []
for sym in tickers:
    try:
        frame = raw[sym] if len(tickers) > 1 else raw
        frame = frame.dropna(how="all")
        if len(frame) < 2:
            continue
        last = float(frame["Close"].iloc[-1])
        prev = float(frame["Close"].iloc[-2])
        chg = (last - prev) / prev * 100
        vol = int(frame["Volume"].iloc[-1])
        rows.append((sym, last, chg, vol))
    except Exception:
        pass
rows.sort(key=lambda x: abs(x[2]), reverse=True)
print(f"BOOK: {len(tickers)} tickers")
print(f"{'Sym':<6} {'Px':>8} {'Chg%':>7} {'Vol':>12}")
for sym, last, chg, vol in rows[:25]:
    print(f"{sym:<6} {last:>8.2f} {chg:>+6.2f}% {vol:>12,}")
