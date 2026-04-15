"""
Web tools — search, fetch pages, and global news briefings.
"""

import httpx
import xml.etree.ElementTree as ET
import asyncio  # Required for parallel execution
import re
from datetime import datetime

SEED_FEEDS = [
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    'https://www.cnbc.com/id/100727362/device/rss/rss.html',
    'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    'https://www.aljazeera.com/xml/rss/all.xml'
]

async def fetch_and_parse_feed(client, url):
    """Helper function to handle a single feed request and parse its XML."""
    try:
        response = await client.get(url, headers={'User-Agent': 'Friday-AI/1.0'}, timeout=5.0)
        if response.status_code != 200:
            return []

        root = ET.fromstring(response.content)
        # Extract source name from URL (e.g., 'BBC' or 'NYTIMES')
        source_name = url.split('.')[1].upper()
        
        feed_items = []
        # Get top 5 items per feed
        items = root.findall(".//item")[:5]
        for item in items:
            title = item.findtext("title")
            description = item.findtext("description")
            link = item.findtext("link")
            
            if description:
                description = re.sub('<[^<]+?>', '', description).strip()

            feed_items.append({
                "source": source_name,
                "title": title,
                "summary": description[:200] + "..." if description else "",
                "link": link
            })
        return feed_items
    except Exception:
        # If one feed fails, return an empty list so others can still succeed
        return []

def register(mcp):

    @mcp.tool()
    async def get_world_news() -> str:
        """
        Fetches the latest global headlines from major news outlets simultaneously.
        Use this when the user asks 'What's going on in the world?' or for recent events.
        """
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            # 1. Create a list of 'tasks' (one for each URL)
            tasks = [fetch_and_parse_feed(client, url) for url in SEED_FEEDS]
            
            # 2. Fire them all at once and wait for the results
            # results will be a list of lists: [[news from bbc], [news from nyt], ...]
            results_of_lists = await asyncio.gather(*tasks)
            
            # 3. Flatten the list of lists into a single list of articles
            all_articles = [item for sublist in results_of_lists for item in sublist]

        if not all_articles:
            return "The global news grid is unresponsive, sir. I'm unable to pull headlines."

        # 4. Format the final briefing
        report = ["### GLOBAL NEWS BRIEFING (LIVE)\n"]
        # Limit to top 12 items so the AI doesn't get overwhelmed
        for entry in all_articles[:12]:
            report.append(f"**[{entry['source']}]** {entry['title']}")
            report.append(f"{entry['summary']}")
            report.append(f"Link: {entry['link']}\n")

        return "\n".join(report)

    @mcp.tool()
    async def search_web(query: str) -> str:
        """Search the web for a query using DuckDuckGo and return a results summary."""
        ddg_url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}

        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(ddg_url, params=params)
            resp.raise_for_status()
            data = resp.json()

        lines = [f"### Web results for: {query}\n"]

        if abstract := data.get("AbstractText"):
            lines.append(f"**Summary:** {abstract}")
            if src := data.get("AbstractSource"):
                lines.append(f"Source: {src} — {data.get('AbstractURL', '')}\n")

        if answer := data.get("Answer"):
            lines.append(f"**Direct answer:** {answer}\n")

        topics = data.get("RelatedTopics", [])[:5]
        if topics:
            lines.append("**Related:**")
            for t in topics:
                if text := t.get("Text"):
                    lines.append(f"- {text}")

        if len(lines) == 1:
            return f"No clear results for '{query}', sir. Try rephrasing."

        return "\n".join(lines)

    @mcp.tool()
    async def fetch_url(url: str) -> str:
        """
        Fetch and return readable plain text from a URL, stripping all HTML tags.
        Use when the boss asks to read a specific article or page.
        """
        headers = {"User-Agent": "Mozilla/5.0 (Friday-AI/2.0)"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=10, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        # Strip tags, collapse whitespace, cap length
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text[:3000] + ("\n\n[truncated]" if len(text) > 3000 else "")
    
    @mcp.tool()
    async def open_world_monitor() -> str:
        """
        Opens the World Monitor dashboard (worldmonitor.app) in the system's web browser.
        Use this when the user wants a visual overview of global events or a real-time map.
        """
        import webbrowser
        url = "https://worldmonitor.app/"
        
        try:
            # This opens the URL in the default browser (Chrome/Edge/Safari)
            webbrowser.open(url)
            return "Displaying the World Monitor on your primary screen now, sir."
        except Exception as e:
            return f"I'm unable to initialize the visual monitor: {str(e)}"