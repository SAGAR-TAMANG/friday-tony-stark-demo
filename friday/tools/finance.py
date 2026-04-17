"""
Finance tools — stock quotes, market overview, crypto prices.
Primary: yfinance (no key) + CoinGecko public API (no key).
"""

import asyncio
from typing import Any

import httpx

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Common tickers → CoinGecko IDs. Extend as needed.
CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
}

INDEX_TICKERS = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI"}


def _yf_quote_sync(ticker: str) -> dict[str, Any]:
    import yfinance as yf  # Imported lazily — heavy dependency.

    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    hist = t.history(period="2d")
    if hist.empty:
        return {"ticker": ticker, "error": "No data"}
    last = hist["Close"].iloc[-1]
    prev = hist["Close"].iloc[-2] if len(hist) > 1 else last
    change = last - prev
    pct = (change / prev * 100) if prev else 0.0
    info = getattr(t, "info", {}) or {}
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": round(float(last), 2),
        "change": round(float(change), 2),
        "pct_change": round(float(pct), 2),
        "currency": info.get("currency", "USD"),
    }


async def _yf_quote(ticker: str) -> dict[str, Any]:
    return await asyncio.to_thread(_yf_quote_sync, ticker)


async def _coingecko_price(coin_ids: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"{COINGECKO_BASE}/simple/price",
            params={"ids": ",".join(coin_ids), "vs_currencies": "usd", "include_24hr_change": "true"},
        )
        r.raise_for_status()
        return r.json()


def _format_quote(q: dict[str, Any]) -> str:
    if q.get("error"):
        return f"{q['ticker']}: no data ({q['error']})."
    arrow = "▲" if q["change"] >= 0 else "▼"
    return (
        f"{q['name']} ({q['ticker']}): "
        f"{q['price']:,.2f} {q['currency']} {arrow} "
        f"{q['change']:+.2f} ({q['pct_change']:+.2f}%)"
    )


def register(mcp):

    @mcp.tool()
    async def get_stock_quote(ticker: str) -> str:
        """Live quote for a single ticker (e.g. 'TSLA', 'AAPL', 'RELIANCE.NS')."""
        quote = await _yf_quote(ticker)
        return _format_quote(quote)

    @mcp.tool()
    async def get_market_overview() -> str:
        """Snapshot of major US indices: S&P 500, Nasdaq, Dow."""
        quotes = await asyncio.gather(*(_yf_quote(sym) for sym in INDEX_TICKERS.values()))
        return "\n".join(_format_quote(q) for q in quotes)

    @mcp.tool()
    async def get_crypto_price(symbol: str) -> str:
        """Live crypto price. Accepts tickers like 'BTC', 'ETH', 'SOL'."""
        key = symbol.upper().strip()
        coin_id = CRYPTO_ID_MAP.get(key, symbol.lower())
        try:
            data = await _coingecko_price([coin_id])
        except Exception as exc:
            return f"Crypto feed error: {exc}"
        entry = data.get(coin_id)
        if not entry:
            return f"No CoinGecko entry for {symbol!r}."
        price = entry.get("usd", 0)
        change_24h = entry.get("usd_24h_change", 0) or 0
        arrow = "▲" if change_24h >= 0 else "▼"
        return f"{key}: ${price:,.2f} USD {arrow} {change_24h:+.2f}% (24h)"
