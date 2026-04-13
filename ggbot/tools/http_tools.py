from __future__ import annotations

import html
import re
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

    return http_get,