"""
Finance tools — real-time stock quotes via Yahoo Finance (no API key required).
"""

import httpx

_YAHOO_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Friday-AI/2.0)"}


def _fmt_quote(q: dict) -> str:
    """Format a Yahoo Finance quote dict into a spoken FRIDAY-style sentence."""
    ticker = q.get("symbol", "?")
    name = q.get("longName") or q.get("shortName") or ticker
    price = q.get("regularMarketPrice")
    change = q.get("regularMarketChange", 0.0)
    pct = q.get("regularMarketChangePercent", 0.0)
    mktcap = q.get("marketCap")

    direction = "up" if change >= 0 else "down"
    cap_str = ""
    if mktcap:
        cap_str = f" Market cap ${mktcap / 1e9:.1f}B." if mktcap >= 1e9 else ""

    return (
        f"{name} ({ticker}) is at ${price:.2f}, "
        f"{direction} {abs(change):.2f} ({abs(pct):.2f}%) today.{cap_str}"
    )


def register(mcp):

    @mcp.tool()
    async def get_stock_price(ticker: str) -> str:
        """
        Get the latest stock price and daily change for a ticker symbol.
        Examples: AAPL, TSLA, NVDA, GOOGL, AMZN, MSFT, ^DJI (Dow Jones).
        Use when the boss asks about specific stocks or market indices.
        """
        async with httpx.AsyncClient(timeout=8, headers=_HEADERS) as client:
            resp = await client.get(_YAHOO_URL, params={"symbols": ticker.upper()})
            resp.raise_for_status()
            quotes = resp.json().get("quoteResponse", {}).get("result", [])

        if not quotes:
            return f"Couldn't pull a quote for '{ticker}', sir. Double-check that ticker."

        return _fmt_quote(quotes[0])

    @mcp.tool()
    async def get_market_overview() -> str:
        """
        Get a quick snapshot of major US market indices: S&P 500, Dow Jones, NASDAQ.
        Use when the boss asks for a market overview or 'how are the markets doing'.
        """
        symbols = "^GSPC,^DJI,^IXIC"
        async with httpx.AsyncClient(timeout=8, headers=_HEADERS) as client:
            resp = await client.get(_YAHOO_URL, params={"symbols": symbols})
            resp.raise_for_status()
            quotes = resp.json().get("quoteResponse", {}).get("result", [])

        if not quotes:
            return "Market data is down, sir. Feeds are unresponsive."

        lines = ["### MARKET SNAPSHOT"]
        for q in quotes:
            lines.append(_fmt_quote(q))
        return "\n".join(lines)
