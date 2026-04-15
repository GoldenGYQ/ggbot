from __future__ import annotations

import html
import re
from urllib.parse import urljoin
from typing import Any, cast

import httpx
from pydantic import BaseModel, Field

from .context import ToolContext
from .registry import tool


class HttpGetArgs(BaseModel):
    url: str = Field(..., description="Absolute URL to fetch")
    timeout_s: float = Field(10.0, ge=0.5, le=60.0, description="Request timeout in seconds")
    headers: dict[str, str] | None = Field(None, description="Optional request headers")
    params: dict[str, str] | None = Field(None, description="Optional query parameters")
    max_chars: int = Field(20_000, ge=1000, le=200_000, description="Max chars of response text returned")


class DuckDuckGoSearchArgs(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(5, ge=1, le=20, description="Maximum results")


class NewsSearchArgs(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(5, ge=1, le=20, description="Maximum search results")
    fetch_top_k: int = Field(3, ge=0, le=10, description="Fetch top K result pages")
    excerpt_chars: int = Field(300, ge=50, le=5000, description="Excerpt length")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…(truncated, {len(text) - limit} chars omitted)"


def _strip_tags(s: str) -> str:
    s = re.sub(r"<script.*?</script>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style.*?</style>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_duckduckgo_html(html_text: str, max_results: int) -> list[dict[str, str]]:
    links = re.findall(
        r'<a[^>]*class=["\']result-link["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = re.findall(
        r'<div[^>]*class=["\']result-snippet["\'][^>]*>(.*?)</div>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results: list[dict[str, str]] = []
    for i, (href, title_html) in enumerate(links[:max_results]):
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(
            {
                "title": _strip_tags(title_html),
                "url": href,
                "snippet": _strip_tags(snippet),
            }
        )
    return results


def _extract_title_and_excerpt(page_html: str, excerpt_chars: int) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    title = _strip_tags(title_match.group(1)) if title_match else ""
    text = _strip_tags(page_html)
    excerpt = text[:excerpt_chars]
    return title, excerpt


def make_http_tools(*, transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None):
    async_transport = cast(httpx.AsyncBaseTransport | None, transport)

    @tool()
    async def http_get(ctx: ToolContext, args: HttpGetArgs) -> dict[str, Any]:
        """Fetch a URL over HTTP(S) and return status + truncated text."""

        ctx.emit(
            "status",
            {
                "message": f"Fetching {args.url}",
                "stage": "http",
            },
        )

        async with httpx.AsyncClient(follow_redirects=True, transport=async_transport) as client:
            resp = await client.get(
                args.url,
                headers=args.headers,
                params=args.params,
                timeout=args.timeout_s,
            )

        text = resp.text or ""
        text = _truncate(text, args.max_chars)
        return {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "text": text,
        }

    @tool(name="duckduckgo_search", description="Search with DuckDuckGo and return result links/snippets.", input_model=DuckDuckGoSearchArgs)
    async def duckduckgo_search(ctx: ToolContext, args: DuckDuckGoSearchArgs) -> dict[str, Any]:
        ctx.emit("status", {"message": f"Searching DuckDuckGo: {args.query}", "stage": "search"})

        async with httpx.AsyncClient(follow_redirects=True, transport=async_transport) as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": args.query},
                timeout=10.0,
            )

        results = _parse_duckduckgo_html(resp.text or "", args.max_results)
        return {
            "query": args.query,
            "results": results,
        }

    @tool(name="news_search", description="Search news and fetch top-k pages for title/excerpt.", input_model=NewsSearchArgs)
    async def news_search(ctx: ToolContext, args: NewsSearchArgs) -> dict[str, Any]:
        base = await duckduckgo_search(
            ctx,
            DuckDuckGoSearchArgs(query=args.query, max_results=args.max_results),
        )
        results = list(base.get("results", []))
        fetch_k = min(max(args.fetch_top_k, 0), len(results))

        async with httpx.AsyncClient(follow_redirects=True, transport=async_transport) as client:
            for item in results[:fetch_k]:
                url = str(item.get("url", ""))
                try:
                    resp = await client.get(url, timeout=10.0)
                    page_title, excerpt = _extract_title_and_excerpt(resp.text or "", args.excerpt_chars)
                    item["fetch"] = {
                        "final_url": str(resp.url),
                        "status_code": resp.status_code,
                        "page_title": page_title,
                        "excerpt": excerpt,
                    }
                except Exception as e:
                    item["fetch"] = {
                        "final_url": url,
                        "status_code": 0,
                        "page_title": "",
                        "excerpt": "",
                        "error": str(e),
                    }

        return {
            "query": args.query,
            "fetched_top_k": fetch_k,
            "results": results,
        }

    return http_get, duckduckgo_search, news_search