"""Web Search client for PolyEdge - real-time event research for market predictions.

Supports:
- Tavily API (premium, requires TAVILY_API_KEY)
- DuckDuckGo HTML scraping (free fallback, no API key needed)
"""

import httpx
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# DuckDuckGo HTML endpoint (no API key required)
DDG_HTML_URL = "https://html.duckduckgo.com/html/"

# Tavily API endpoint
TAVILY_API_URL = "https://api.tavily.com/search"


@dataclass
class SearchResult:
    """Single search result."""

    title: str
    url: str
    content: str
    score: float = 0.0
    published_date: Optional[str] = None


@dataclass
class WebSearchResponse:
    """Aggregated search response."""

    query: str
    results: List[SearchResult] = field(default_factory=list)
    source: str = "unknown"  # "tavily" or "duckduckgo"
    searched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_context_string(self, max_results: int = 5) -> str:
        """Convert search results to a context string for AI consumption."""
        if not self.results:
            return ""

        lines = [f"[Web Search: {self.query}]"]
        for i, r in enumerate(self.results[:max_results], 1):
            snippet = r.content[:300] + "..." if len(r.content) > 300 else r.content
            lines.append(f"{i}. {r.title}: {snippet}")

        return "\n".join(lines)


class WebSearchClient:
    """
    Web search client with Tavily (premium) and DuckDuckGo (free) backends.

    Usage:
        client = WebSearchClient()
        response = await client.search("Trump election odds")
        context = response.to_context_string()
    """

    def __init__(self, timeout: float = 15.0):
        self.tavily_api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @property
    def is_enabled(self) -> bool:
        """Always enabled - DuckDuckGo fallback requires no API key."""
        return True

    @property
    def has_tavily(self) -> bool:
        """Check if Tavily API key is configured."""
        return bool(self.tavily_api_key)

    async def _search_tavily(
        self, query: str, max_results: int = 5
    ) -> WebSearchResponse:
        """Search using Tavily API (premium, better quality)."""
        client = await self._get_client()

        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": max_results,
        }

        try:
            resp = await client.post(TAVILY_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        score=item.get("score", 0.0),
                        published_date=item.get("published_date"),
                    )
                )

            return WebSearchResponse(
                query=query,
                results=results,
                source="tavily",
            )
        except Exception as e:
            logger.warning("Tavily search failed: %s, falling back to DuckDuckGo", e)
            return await self._search_duckduckgo(query, max_results)

    async def _search_duckduckgo(
        self, query: str, max_results: int = 5
    ) -> WebSearchResponse:
        """Search using DuckDuckGo HTML scraping (free, no API key)."""
        client = await self._get_client()

        try:
            # DuckDuckGo HTML form POST
            resp = await client.post(
                DDG_HTML_URL,
                data={"q": query, "b": ""},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            html = resp.text

            results = self._parse_ddg_html(html, max_results)

            return WebSearchResponse(
                query=query,
                results=results,
                source="duckduckgo",
            )
        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return WebSearchResponse(query=query, results=[], source="duckduckgo")

    def _parse_ddg_html(self, html: str, max_results: int) -> List[SearchResult]:
        """Parse DuckDuckGo HTML response to extract search results."""
        results = []

        # Pattern for result links: class="result__a" href="..."
        link_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE
        )

        # Pattern for snippets: class="result__snippet"
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)</[^>]+>',
            re.IGNORECASE | re.DOTALL,
        )

        # Find all result blocks
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html,
            re.IGNORECASE | re.DOTALL,
        )

        # Simpler approach: find links and snippets separately
        links = link_pattern.findall(html)
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL
        )

        for i, (url, title) in enumerate(links[:max_results]):
            # Clean up URL (DuckDuckGo wraps URLs)
            if "uddg=" in url:
                # Extract actual URL from DuckDuckGo redirect
                match = re.search(r"uddg=([^&]+)", url)
                if match:
                    import urllib.parse

                    url = urllib.parse.unquote(match.group(1))

            # Get corresponding snippet if available
            content = ""
            if i < len(snippets):
                # Clean HTML tags from snippet
                content = re.sub(r"<[^>]+>", "", snippets[i]).strip()

            if title.strip() and url.strip():
                results.append(
                    SearchResult(
                        title=title.strip(),
                        url=url.strip(),
                        content=content,
                        score=1.0 - (i * 0.1),  # Decreasing relevance score
                    )
                )

        return results

    async def search(self, query: str, max_results: int = 5) -> WebSearchResponse:
        """
        Search the web for information.

        Uses Tavily if API key available, otherwise falls back to DuckDuckGo.
        """
        if self.has_tavily:
            return await self._search_tavily(query, max_results)
        return await self._search_duckduckgo(query, max_results)

    async def search_for_market(self, question: str, max_results: int = 3) -> str:
        """
        Search for information relevant to a prediction market question.

        Optimizes the query for prediction market research and returns
        a context string suitable for AI analysis.

        Args:
            question: The market question (e.g., "Will Trump win 2024 election?")
            max_results: Maximum number of results to include

        Returns:
            Context string for AI consumption, or empty string on failure
        """
        # Optimize query for current events/predictions
        # Remove common market question patterns
        clean_query = question
        for pattern in ["Will ", "Will the ", "What will ", "?", "by ", "before "]:
            clean_query = clean_query.replace(pattern, " ")

        # Add recency signal
        search_query = f"{clean_query.strip()} latest news"

        try:
            response = await self.search(search_query, max_results)
            return response.to_context_string(max_results)
        except Exception as e:
            logger.debug("search_for_market failed for '%s': %s", question, e)
            return ""

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_websearch_instance: Optional[WebSearchClient] = None


def get_websearch() -> WebSearchClient:
    """Get the singleton WebSearchClient instance."""
    global _websearch_instance
    if _websearch_instance is None:
        _websearch_instance = WebSearchClient()
    return _websearch_instance


async def close_websearch():
    """Close the singleton WebSearchClient."""
    global _websearch_instance
    if _websearch_instance is not None:
        await _websearch_instance.close()
        _websearch_instance = None
