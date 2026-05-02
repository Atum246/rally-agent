"""
🟣 Rally Agent — Built-in Web Search
Real web search without external APIs.
"""

import asyncio
import re
import json
from typing import Optional

from cli.theme import Theme


class WebSearchEngine:
    """Built-in web search using multiple methods"""

    def __init__(self, config):
        self.config = config

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        """Search the web using available methods"""
        results = []

        # Method 1: DuckDuckGo Instant Answers
        ddg_results = await self._search_duckduckgo(query)
        if ddg_results:
            results.extend(ddg_results)

        # Method 2: DuckDuckGo HTML (fallback)
        if not results:
            html_results = await self._search_duckduckgo_html(query)
            if html_results:
                results.extend(html_results)

        return results[:num_results]

    async def _search_duckduckgo(self, query: str) -> list[dict]:
        """Search using DuckDuckGo Instant Answer API"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
                )
                data = resp.json()
                results = []

                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", "Result"),
                        "snippet": data["Abstract"],
                        "url": data.get("AbstractURL", ""),
                        "source": data.get("AbstractSource", "DuckDuckGo"),
                    })

                for topic in data.get("RelatedTopics", [])[:5]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:80],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", ""),
                            "source": "DuckDuckGo",
                        })

                return results
        except Exception:
            return []

    async def _search_duckduckgo_html(self, query: str) -> list[dict]:
        """Search using DuckDuckGo HTML scraping"""
        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers=headers,
                )
                html = resp.text

                results = []
                # Parse results from HTML
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
                urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)

                for i in range(min(len(titles), len(snippets), 5)):
                    title = re.sub(r'<[^>]+>', '', titles[i]).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                    url = re.sub(r'<[^>]+>', '', urls[i]).strip() if i < len(urls) else ""

                    if title and snippet:
                        results.append({
                            "title": title,
                            "snippet": snippet,
                            "url": url,
                            "source": "DuckDuckGo",
                        })

                return results
        except Exception:
            return []

    async def search_news(self, query: str) -> list[dict]:
        """Search for recent news"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": f"{query} news", "kl": "us-en"},
                )
                html = resp.text
                results = []
                snippets = re.findall(r'class="result-snippet">(.*?)</td>', html, re.DOTALL)
                titles = re.findall(r'class="result-link"[^>]*>(.*?)</a>', html, re.DOTALL)

                for i in range(min(len(titles), len(snippets), 5)):
                    title = re.sub(r'<[^>]+>', '', titles[i]).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                    if title:
                        results.append({"title": title, "snippet": snippet, "source": "News"})

                return results
        except Exception:
            return []

    async def fetch_page(self, url: str, max_chars: int = 10000) -> str:
        """Fetch and extract text from a URL"""
        try:
            import httpx
            headers = {"User-Agent": "Mozilla/5.0 (compatible; RallyAgent/1.0)"}
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                html = resp.text

                # Strip HTML tags
                text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

                return text[:max_chars]
        except Exception as e:
            return f"Error fetching page: {e}"

    async def get_weather(self, location: str = "") -> str:
        """Get current weather"""
        try:
            import httpx
            location = location or "auto:ip"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://wttr.in/{location}?format=3")
                return resp.text.strip()
        except Exception:
            return "Weather unavailable"

    async def get_news_headlines(self) -> list[str]:
        """Get current news headlines"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://lite.duckduckgo.com/lite/", params={"q": "today news headlines"})
                html = resp.text
                titles = re.findall(r'class="result-link"[^>]*>(.*?)</a>', html)
                return [re.sub(r'<[^>]+>', '', t).strip() for t in titles[:10] if t.strip()]
        except Exception:
            return []
