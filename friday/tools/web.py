"""
Web tools — real-time web search and URL fetching.
News moved to friday/tools/news.py (GDELT + RSS fallback).
"""

import os
import re

import httpx


async def _search_tavily(query: str, n: int) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": n, "search_depth": "basic"},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("content", "")[:240]}
        for h in data.get("results", [])[:n]
    ]


async def _search_brave(query: str, n: int) -> list[dict]:
    api_key = os.getenv("BRAVE_API_KEY", "")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": n},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("description", "")[:240]}
        for h in data.get("web", {}).get("results", [])[:n]
    ]


async def _search_ddg(query: str, n: int) -> list[dict]:
    # DuckDuckGo HTML endpoint — no key, async-friendly.
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        r = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Friday-AI/2.0"},
        )
        r.raise_for_status()
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    hits = []
    for url, title, snippet in pattern.findall(r.text)[:n]:
        clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
        hits.append({"title": clean(title), "url": url, "snippet": clean(snippet)[:240]})
    return hits


async def _run_search(query: str, n: int) -> list[dict]:
    for backend in (_search_tavily, _search_brave, _search_ddg):
        try:
            hits = await backend(query, n)
            if hits:
                return hits
        except Exception:
            continue
    return []


def register(mcp):

    @mcp.tool()
    async def search_web(query: str, max_results: int = 5) -> str:
        """
        Search the web for a query. Returns ranked snippets.
        Backend order: Tavily → Brave → DuckDuckGo. Uses whichever key is present.
        """
        hits = await _run_search(query, max_results)
        if not hits:
            return f"Search came back empty for: {query!r}."
        lines = [f"Search results for '{query}':\n"]
        for i, r in enumerate(hits, 1):
            lines.append(f"[{i}] {r['title']}\n    {r['snippet']}\n    {r['url']}")
        return "\n".join(lines)

    @mcp.tool()
    async def fetch_url(url: str) -> str:
        """Fetch the raw text content of a URL (truncated to 4000 chars)."""
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text[:4000]

    @mcp.tool()
    async def open_world_monitor() -> str:
        """Open the worldmonitor.app dashboard in the local browser for a visual overview."""
        import webbrowser
        try:
            webbrowser.open("https://worldmonitor.app/")
            return "Displaying the World Monitor on your primary screen now, boss."
        except Exception as e:
            return f"Unable to initialize the visual monitor: {e}"
