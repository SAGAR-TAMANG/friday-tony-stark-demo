"""
News tools — GDELT 2.0 DOC API (primary, free, multi-language, 15-min cadence)
with RSS fallback. Replaces the RSS-only `get_world_news` from web.py.
"""

import asyncio
from typing import Any

import feedparser
import httpx

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

RSS_FALLBACK_FEEDS = [
    ("BBC",        "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NYT",        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("ALJAZEERA",  "https://www.aljazeera.com/xml/rss/all.xml"),
    ("REUTERS",    "https://www.reutersagency.com/feed/?best-topics=world&post_type=best"),
    ("HINDU",      "https://www.thehindu.com/news/international/feeder/default.rss"),
]


async def _gdelt_query(query: str, max_records: int = 12) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "datedesc",
    }
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(GDELT_ENDPOINT, params=params)
        if r.status_code != 200 or not r.text.strip():
            return []
        try:
            data = r.json()
        except Exception:
            return []
    return [
        {
            "source": a.get("sourcecountry", "") or a.get("domain", ""),
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "seendate": a.get("seendate", ""),
            "language": a.get("language", ""),
        }
        for a in data.get("articles", [])
    ]


async def _fetch_rss(source: str, url: str) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Friday-AI/2.0"})
            r.raise_for_status()
    except Exception:
        return []
    parsed = feedparser.parse(r.content)
    return [
        {
            "source": source,
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": entry.get("summary", "")[:200],
        }
        for entry in parsed.entries[:5]
    ]


async def _rss_briefing() -> list[dict[str, Any]]:
    tasks = [_fetch_rss(src, url) for src, url in RSS_FALLBACK_FEEDS]
    results = await asyncio.gather(*tasks)
    return [item for batch in results for item in batch]


def _format_briefing(articles: list[dict[str, Any]], header: str) -> str:
    if not articles:
        return "The global news grid is unresponsive, boss. I'm unable to pull headlines."
    lines = [f"### {header}\n"]
    for a in articles[:12]:
        src = a.get("source", "?")
        lines.append(f"**[{src}]** {a.get('title', '')}")
        if a.get("summary"):
            lines.append(a["summary"])
        if a.get("url"):
            lines.append(f"Link: {a['url']}\n")
    return "\n".join(lines)


def register(mcp):

    @mcp.tool()
    async def get_world_news() -> str:
        """Top global headlines right now. Tries GDELT first, falls back to RSS."""
        articles = await _gdelt_query("sourcelang:english", max_records=12)
        if not articles:
            articles = await _rss_briefing()
        return _format_briefing(articles, "GLOBAL NEWS BRIEFING (LIVE)")

    @mcp.tool()
    async def get_news_by_topic(topic: str) -> str:
        """Latest stories on a specific topic. Uses GDELT full-text search."""
        articles = await _gdelt_query(topic, max_records=10)
        return _format_briefing(articles, f"NEWS — {topic.upper()}")

    @mcp.tool()
    async def get_trending_events() -> str:
        """Highest-volume world events in the last 24h (GDELT tone-weighted)."""
        articles = await _gdelt_query("sourcelang:english", max_records=20)
        if not articles:
            return "Trending feed unavailable, boss."
        # GDELT's datedesc already surfaces the freshest; dedupe by source for variety.
        seen, picked = set(), []
        for a in articles:
            key = a.get("source", "") or a.get("url", "")
            if key in seen:
                continue
            seen.add(key)
            picked.append(a)
            if len(picked) >= 10:
                break
        return _format_briefing(picked, "TRENDING EVENTS (LAST 24H)")
