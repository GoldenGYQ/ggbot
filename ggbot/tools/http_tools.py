from __future__ import annotations

import html
import re
import asyncio
from typing import Any, cast
from urllib.parse import urlencode

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
    query: str = Field(..., min_length=1, description="Search query")
    max_results: int = Field(5, ge=1, le=10, description="Max results")
    region: str | None = Field(
        None,
        description="Optional region code (DuckDuckGo 'kl'), e.g. 'us-en', 'cn-zh'",
    )
    safe: bool = Field(True, description="Enable safe search")


class NewsSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    max_results: int = Field(8, ge=1, le=10, description="Max search results")
    fetch_top_k: int = Field(3, ge=1, le=8, description="Fetch and summarize top K results")
    region: str | None = Field(
        None,
        description="Optional region code (DuckDuckGo 'kl'), e.g. 'us-en', 'cn-zh'",
    )
    safe: bool = Field(True, description="Enable safe search")
    timeout_s: float = Field(12.0, ge=0.5, le=60.0, description="Per-request timeout in seconds")
    concurrency: int = Field(3, ge=1, le=8, description="Max concurrent fetches")
    max_chars_each: int = Field(12_000, ge=1000, le=100_000, description="Max chars fetched per page")
    excerpt_chars: int = Field(1200, ge=200, le=5000, description="Chars of extracted text excerpt")


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


def _extract_html_title(html_text: str) -> str:
    m = re.search(r"<title[^>]*>(?P<t>.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return _strip_tags(m.group("t"))


def _extract_text_excerpt(html_text: str, *, limit: int) -> str:
    text = _strip_tags(html_text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _parse_ddg_lite_html(html_text: str, *, max_results: int) -> list[dict[str, str]]:
    # DuckDuckGo lite format is relatively stable: results are links with class="result-link".
    out: list[dict[str, str]] = []

    # Find anchors; keep it dependency-free (no BeautifulSoup).
    for m in re.finditer(
        r"<a[^>]+class=\"result-link\"[^>]+href=\"(?P<href>[^\"]+)\"[^>]*>(?P<title>.*?)</a>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href = html.unescape(m.group("href")).strip()
        title = _strip_tags(m.group("title"))

        snippet = ""
        # Heuristic: snippet often appears soon after the link in a result-snippet span.
        tail = html_text[m.end() : m.end() + 1200]
        sm = re.search(r"result-snippet\"[^>]*>(?P<s>.*?)</", tail, flags=re.IGNORECASE | re.DOTALL)
        if sm:
            snippet = _strip_tags(sm.group("s"))

        if href and title:
            out.append({"title": title, "url": href, "snippet": snippet})
        if len(out) >= max_results:
            break

    return out


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

    @tool()
    async def duckduckgo_search(ctx: ToolContext, args: DuckDuckGoSearchArgs) -> dict[str, Any]:
        """Search the web via DuckDuckGo (lite HTML) and return top results."""

        ctx.emit(
            "status",
            {
                "message": f"Searching DuckDuckGo: {args.query}",
                "stage": "search",
            },
        )

        base = "https://lite.duckduckgo.com/lite/"
        params: dict[str, str] = {"q": args.query}
        if args.region:
            params["kl"] = args.region
        if args.safe:
            params["kp"] = "1"
        else:
            params["kp"] = "-1"

        url = base + "?" + urlencode(params)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            transport=async_transport,
            headers=headers,
            timeout=30.0
        ) as client:
            resp = await client.get(url)

        # 检查响应状态
        if resp.status_code != 200:
            ctx.emit(
                "status",
                {
                    "message": f"DuckDuckGo搜索失败: 状态码 {resp.status_code}",
                    "stage": "search_error",
                },
            )
            # 返回空结果而不是失败
            return {
                "query": args.query,
                "results": [],
                "fetched_url": url,
                "error": f"HTTP {resp.status_code}",
            }

        results = _parse_ddg_lite_html(resp.text or "", max_results=args.max_results)
        return {
            "query": args.query,
            "results": results,
            "fetched_url": url,
        }

    @tool()
    async def news_search(ctx: ToolContext, args: NewsSearchArgs) -> dict[str, Any]:
        """Search DuckDuckGo and fetch+summarize the top results (async + concurrent)."""

        # 1) Search
        ddg = await duckduckgo_search(
            ctx,
            DuckDuckGoSearchArgs(
                query=args.query,
                max_results=args.max_results,
                region=args.region,
                safe=args.safe,
            ),
        )

        results = list(ddg.get("results") or [])
        top_k = min(args.fetch_top_k, len(results))

        ctx.emit(
            "status",
            {
                "message": f"Fetching top {top_k} pages for: {args.query}",
                "stage": "fetch",
                "percent": 0,
            },
        )

        sem = asyncio.Semaphore(args.concurrency)
        fetched: list[dict[str, Any]] = [None] * top_k  # type: ignore[list-item]
        done = 0

        async with httpx.AsyncClient(follow_redirects=True, transport=async_transport) as client:

            async def fetch_one(i: int, item: dict[str, Any]) -> None:
                nonlocal done
                url = str(item.get("url") or "")
                if not url:
                    fetched[i] = {"error": "missing url"}
                    return

                async with sem:
                    try:
                        resp = await client.get(url, timeout=args.timeout_s)
                        text = resp.text or ""
                        text = _truncate(text, args.max_chars_each)
                        page_title = _extract_html_title(text)
                        excerpt = _extract_text_excerpt(text, limit=args.excerpt_chars)
                        fetched[i] = {
                            "requested_url": url,
                            "final_url": str(resp.url),
                            "status_code": resp.status_code,
                            "page_title": page_title,
                            "excerpt": excerpt,
                        }
                    except Exception as e:
                        fetched[i] = {
                            "requested_url": url,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    finally:
                        done += 1
                        percent = int(done / max(top_k, 1) * 100)
                        ctx.emit(
                            "status",
                            {
                                "message": f"Fetched {done}/{top_k} pages",
                                "stage": "fetch",
                                "percent": percent,
                            },
                        )

            await asyncio.gather(*(fetch_one(i, results[i]) for i in range(top_k)))

        # 3) Merge search result + fetched summary
        merged: list[dict[str, Any]] = []
        for i, r in enumerate(results):
            item = {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": r.get("snippet") or "",
            }
            if i < top_k:
                item["fetch"] = fetched[i]
            merged.append(item)

        return {
            "query": args.query,
            "results": merged,
            "fetched_top_k": top_k,
            "search_url": ddg.get("fetched_url"),
        }

    return http_get, duckduckgo_search, news_search
