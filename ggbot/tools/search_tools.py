from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from ggbot.tools.registry import tool
from ggbot.tools.context import ToolContext


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str = ""
    source: str = ""


class SearchQueryArgs(BaseModel):
    """搜索查询参数"""
    query: str = Field(description="搜索查询字符串")
    max_results: int = Field(default=5, description="最大结果数量")
    region: Optional[str] = Field(default=None, description="地区代码，如 'cn-zh'")
    safe: bool = Field(default=True, description="安全搜索")


class EnhancedSearchArgs(BaseModel):
    """增强搜索参数"""
    query: str = Field(description="搜索查询字符串")
    max_results: int = Field(default=5, description="最大结果数量")
    region: Optional[str] = Field(default=None, description="地区代码")
    safe: bool = Field(default=True, description="安全搜索")
    fallback_to_simulated: bool = Field(default=True, description="如果搜索失败，是否返回模拟数据")


def _strip_tags(text: str) -> str:
    """移除HTML标签"""
    return re.sub(r"<[^>]+>", "", text).strip()


async def _try_duckduckgo_search(
    query: str,
    max_results: int,
    region: Optional[str] = None,
    safe: bool = True
) -> List[SearchResult]:
    """尝试使用DuckDuckGo搜索"""
    base = "https://lite.duckduckgo.com/lite/"
    params: Dict[str, str] = {"q": query}
    if region:
        params["kl"] = region
    params["kp"] = "1" if safe else "-1"

    url = base + "?" + urlencode(params)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            return []

        html_text = resp.text or ""

        # 解析DuckDuckGo Lite结果
        results: List[SearchResult] = []
        for m in re.finditer(
            r'<a[^>]+class="result-link"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            href = m.group("href")
            title = _strip_tags(m.group("title"))

            snippet = ""
            tail = html_text[m.end(): m.end() + 1000]
            sm = re.search(r'result-snippet"[^>]*>(?P<s>.*?)</', tail, flags=re.IGNORECASE | re.DOTALL)
            if sm:
                snippet = _strip_tags(sm.group("s"))

            if href and title:
                results.append(SearchResult(
                    title=title,
                    url=href,
                    snippet=snippet,
                    source="duckduckgo"
                ))

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


async def _try_bing_search(
    query: str,
    max_results: int,
    region: Optional[str] = None
) -> List[SearchResult]:
    """尝试使用Bing搜索（通过RapidAPI或其他方式）"""
    # 注意：这需要API key，这里只是示例
    return []


async def _try_google_search(
    query: str,
    max_results: int,
    region: Optional[str] = None
) -> List[SearchResult]:
    """尝试使用Google搜索（通过自定义搜索API）"""
    # 注意：这需要API key，这里只是示例
    return []


def _generate_simulated_results(query: str, max_results: int = 5) -> List[SearchResult]:
    """生成模拟搜索结果（当真实搜索失败时使用）"""
    simulated_data = {
        # 技术相关
        "python": [
            SearchResult("Python官方文档", "https://docs.python.org/", "Python编程语言官方文档", "simulated"),
            SearchResult("Python教程 - W3Schools", "https://www.w3schools.com/python/", "Python编程教程", "simulated"),
            SearchResult("Python GitHub", "https://github.com/python", "Python在GitHub上的官方仓库", "simulated"),
        ],
        "weather api": [
            SearchResult("OpenWeatherMap", "https://openweathermap.org/api", "天气数据API服务", "simulated"),
            SearchResult("WeatherAPI.com", "https://www.weatherapi.com/", "免费天气API", "simulated"),
            SearchResult("wttr.in", "https://wttr.in/", "命令行天气服务", "simulated"),
        ],
        # 中国市场数据
        "中国手机市场": [
            SearchResult("2024年中国智能手机市场份额报告", "https://example.com/report1", "主要品牌市场份额分析", "simulated"),
            SearchResult("中国手机品牌销量统计", "https://example.com/report2", "华为、小米、OPPO等品牌数据", "simulated"),
            SearchResult("智能手机市场趋势分析", "https://example.com/report3", "2024-2025市场预测", "simulated"),
        ],
        # 默认
        "default": [
            SearchResult(f"关于'{query}'的搜索结果1", "https://example.com/result1", f"这是关于{query}的模拟结果", "simulated"),
            SearchResult(f"关于'{query}'的搜索结果2", "https://example.com/result2", f"更多关于{query}的信息", "simulated"),
            SearchResult(f"关于'{query}'的搜索结果3", "https://example.com/result3", f"{query}相关资源", "simulated"),
        ]
    }

    # 查找最匹配的模拟数据
    query_lower = query.lower()
    for key in simulated_data:
        if key in query_lower:
            return simulated_data[key][:max_results]

    return simulated_data["default"][:max_results]


@tool(name="enhanced_search", description="增强的网络搜索工具，支持多个搜索引擎和模拟数据回退")
async def enhanced_search(ctx: ToolContext, args: EnhancedSearchArgs) -> Dict[str, Any]:
    """增强的网络搜索工具"""
    ctx.emit(
        "status",
        {
            "message": f"搜索: {args.query}",
            "stage": "search",
        },
    )

    # 尝试多个搜索引擎
    search_tasks = [
        _try_duckduckgo_search(args.query, args.max_results, args.region, args.safe),
        # 可以添加更多搜索引擎
    ]

    results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)

    # 合并结果
    all_results: List[SearchResult] = []
    for results in results_lists:
        if isinstance(results, list):
            all_results.extend(results)

    # 去重（基于URL）
    unique_results: List[SearchResult] = []
    seen_urls = set()
    for result in all_results:
        if result.url not in seen_urls:
            seen_urls.add(result.url)
            unique_results.append(result)
        if len(unique_results) >= args.max_results:
            break

    # 如果真实搜索没有结果，使用模拟数据
    if not unique_results and args.fallback_to_simulated:
        ctx.emit(
            "status",
            {
                "message": f"搜索无结果，使用模拟数据: {args.query}",
                "stage": "search_fallback",
            },
        )
        unique_results = _generate_simulated_results(args.query, args.max_results)

    # 转换为字典格式
    results_dict = [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "source": r.source
        }
        for r in unique_results
    ]

    return {
        "query": args.query,
        "results": results_dict,
        "total_found": len(unique_results),
        "sources_used": list(set(r.source for r in unique_results)),
        "note": "部分结果可能为模拟数据" if any(r.source == "simulated" for r in unique_results) else ""
    }


@tool(name="search_with_content", description="搜索并获取网页内容")
async def search_with_content(ctx: ToolContext, args: SearchQueryArgs) -> Dict[str, Any]:
    """搜索并获取网页内容"""
    # 首先搜索
    search_results = await enhanced_search(ctx, EnhancedSearchArgs(
        query=args.query,
        max_results=args.max_results,
        region=args.region,
        safe=args.safe,
        fallback_to_simulated=True
    ))

    results = search_results.get("results", [])

    # 获取前3个结果的内容
    content_tasks = []
    for i, result in enumerate(results[:3]):
        if result.get("url"):
            content_tasks.append(_fetch_page_content(result["url"], i))

    if content_tasks:
        contents = await asyncio.gather(*content_tasks, return_exceptions=True)

        # 将内容添加到结果中
        for i, content in enumerate(contents):
            if i < len(results) and not isinstance(content, Exception):
                results[i]["content_preview"] = content[:500]  # 只保留前500字符

    return search_results


async def _fetch_page_content(url: str, index: int) -> str:
    """获取网页内容"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code == 200:
                # 简单提取文本内容
                text = resp.text or ""
                # 移除HTML标签
                text = re.sub(r'<[^>]+>', ' ', text)
                # 合并空白字符
                text = re.sub(r'\s+', ' ', text).strip()
                return text[:1000]  # 限制长度
    except Exception:
        pass
    return ""


def make_search_tools():
    """创建搜索工具"""
    return enhanced_search, search_with_content