"""Browser automation tool — OpenJarvis pattern with Playwright."""

from __future__ import annotations

from typing import Any

from friday.core.base_tool import BaseTool, ToolRegistry, ToolResult


class _BrowserSession:
    """Manages a shared Playwright browser session (lazy init)."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError("playwright not installed. Install with: pip install playwright")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()

    @property
    def page(self):
        self._ensure_browser()
        return self._page

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._playwright = self._browser = self._page = None


# Global session instance
_session = _BrowserSession()


@ToolRegistry.register("browser_navigate")
class BrowserNavigateTool(BaseTool):
    """Navigate to a URL and extract content."""

    tool_id = "browser_navigate"
    is_local = True

    @property
    def name(self) -> str:
        return "browser_navigate"

    @property
    def description(self) -> str:
        return (
            "Navigate to a URL in a headless browser and return page title and text content. "
            "Use for: JavaScript-heavy sites, dynamic content, screenshots."
        )

    def run(self, url: str = "", wait_for: str = "load") -> ToolResult:
        """Navigate to URL and return content.

        Args:
            url: URL to navigate to
            wait_for: Wait condition ('load', 'domcontentloaded', 'networkidle')
        """
        if not url:
            return ToolResult(tool_name=self.name, success=False, error="No URL provided")

        try:
            page = _session.page
            page.goto(url, wait_until=wait_for)
            title = page.title()
            text = page.inner_text("body")[:8000]  # Limit content
            content = f"Title: {title}\n\nContent:\n{text}"
            return ToolResult(tool_name=self.name, success=True, content=content, metadata={"url": url})
        except ImportError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Playwright not installed. Install with: pip install playwright && playwright install chromium"
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


@ToolRegistry.register("browser_screenshot")
class BrowserScreenshotTool(BaseTool):
    """Take a screenshot of a webpage."""

    tool_id = "browser_screenshot"
    is_local = True

    def __init__(self, output_dir: str = "./screenshots") -> None:
        self.output_dir = output_dir

    @property
    def name(self) -> str:
        return "browser_screenshot"

    @property
    def description(self) -> str:
        return "Navigate to a URL and save a screenshot to disk. Returns the file path."

    def run(self, url: str = "", filename: str = "") -> ToolResult:
        """Take screenshot of URL.

        Args:
            url: URL to screenshot
            filename: Output filename (auto-generated if not provided)
        """
        if not url:
            return ToolResult(tool_name=self.name, success=False, error="No URL provided")

        try:
            from pathlib import Path
            page = _session.page
            page.goto(url, wait_until="load")

            # Generate filename if not provided
            if not filename:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_url = url.replace("://", "_").replace("/", "_")[:50]
                filename = f"screenshot_{safe_url}_{ts}.png"

            output_path = Path(self.output_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output_path))

            return ToolResult(
                tool_name=self.name,
                success=True,
                content=f"Screenshot saved to: {output_path}",
                metadata={"path": str(output_path), "url": url}
            )
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Playwright not installed. Install with: pip install playwright && playwright install chromium"
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


@ToolRegistry.register("browser_extract_links")
class BrowserExtractLinksTool(BaseTool):
    """Extract all links from a webpage."""

    tool_id = "browser_extract_links"
    is_local = True

    @property
    def name(self) -> str:
        return "browser_extract_links"

    @property
    def description(self) -> str:
        return "Extract all clickable links from a webpage with their text and URLs."

    def run(self, url: str = "") -> ToolResult:
        """Extract links from URL."""
        if not url:
            return ToolResult(tool_name=self.name, success=False, error="No URL provided")

        try:
            page = _session.page
            page.goto(url, wait_until="load")

            links = page.eval_on_selector_all("a[href]", """
                elements => elements.map(a => ({
                    text: a.textContent?.trim() || '',
                    href: a.href
                })).filter(l => l.href && !l.href.startsWith('javascript:'))
            """)

            lines = [f"Found {len(links)} links on {url}:\n"]
            for i, link in enumerate(links[:50], 1):  # Limit to 50
                lines.append(f"[{i}] {link['text'][:60]}")
                lines.append(f"    → {link['href'][:100]}")

            return ToolResult(
                tool_name=self.name,
                success=True,
                content="\n".join(lines),
                metadata={"count": len(links), "url": url}
            )
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Playwright not installed"
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


def register(mcp):
    """Register browser tools with MCP server."""
    navigate = BrowserNavigateTool()
    screenshot = BrowserScreenshotTool()
    extract = BrowserExtractLinksTool()

    @mcp.tool()
    async def browser_navigate(url: str, wait_for: str = "load") -> str:
        """Navigate to a URL using a headless browser. Returns page title and content.

        Args:
            url: URL to navigate to (e.g., "https://example.com")
            wait_for: When to consider page loaded ('load', 'domcontentloaded', 'networkidle')
        """
        result = navigate.run(url=url, wait_for=wait_for)
        return result.formatted

    @mcp.tool()
    async def browser_screenshot(url: str, filename: str = "") -> str:
        """Take a screenshot of a webpage and save it.

        Args:
            url: URL to screenshot
            filename: Output filename (auto-generated if empty)
        """
        result = screenshot.run(url=url, filename=filename)
        return result.formatted

    @mcp.tool()
    async def browser_extract_links(url: str) -> str:
        """Extract all links from a webpage.

        Args:
            url: URL to extract links from
        """
        result = extract.run(url=url)
        return result.formatted
