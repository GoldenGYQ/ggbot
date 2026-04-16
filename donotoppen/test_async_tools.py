from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from ggbot.core.transcript import Transcript
from ggbot.tools.context import ToolContext
from ggbot.tools.http_tools import make_http_tools
from ggbot.tools.registry import ToolRegistry
from ggbot.tools.shell_stream_tool import make_shell_stream_tool


def test_duckduckgo_search_parses_results(tmp_path: Path) -> None:
    html = """
    <html><body>
      <a class=\"result-link\" href=\"https://example.com/a\">Result A</a>
      <div class=\"result-snippet\">Snippet A</div>
      <a class=\"result-link\" href=\"https://example.com/b\">Result B</a>
      <div class=\"result-snippet\">Snippet B</div>
    </body></html>
    """.strip()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "duckduckgo" in str(request.url)
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    _, duckduckgo_search, _ = make_http_tools(transport=transport)

    reg = ToolRegistry()
    reg.register_tool(duckduckgo_search)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s", transcript=transcript, workspace_root=tmp_path)

    out = reg.call("duckduckgo_search", {"query": "x", "max_results": 2}, ctx=ctx)
    data = json.loads(out)

    assert data["query"] == "x"
    assert len(data["results"]) == 2
    assert data["results"][0]["title"] == "Result A"
    assert data["results"][0]["url"] == "https://example.com/a"


def test_http_get_returns_status_and_text(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello")

    transport = httpx.MockTransport(handler)
    http_get, _, _ = make_http_tools(transport=transport)

    reg = ToolRegistry()
    reg.register_tool(http_get)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s", transcript=transcript, workspace_root=tmp_path)

    out = reg.call("http_get", {"url": "https://example.test/"}, ctx=ctx)
    data = json.loads(out)

    assert data["status_code"] == 200
    assert "hello" in data["text"]


def test_shell_stream_emits_tool_stream_events(tmp_path: Path) -> None:
    # Quick command; should still emit at least one tool_stream chunk.
    cmd = f"\"{sys.executable}\" -c \"print('a'); print('b')\""

    shell_stream = make_shell_stream_tool(workspace_root=tmp_path)

    reg = ToolRegistry()
    reg.register_tool(shell_stream)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s", transcript=transcript, workspace_root=tmp_path)

    out = reg.call(
        "shell_stream",
        {"command": cmd, "timeout_s": 30.0, "emit_every_ms": 50, "max_output_chars": 20000},
        ctx=ctx,
    )

    assert "exit_code=" in out

    events = list(transcript.iter_events())
    chunks = [
        (ev.get("data") or {}).get("chunk")
        for ev in events
        if ev.get("type") == "tool_stream"
    ]

    joined = "".join([c for c in chunks if isinstance(c, str)])
    assert "a" in joined or "b" in joined


def test_news_search_fetches_top_k_and_extracts_excerpt(tmp_path: Path) -> None:
    ddg_html = """
    <html><body>
      <a class=\"result-link\" href=\"https://example.com/a\">Result A</a>
      <div class=\"result-snippet\">Snippet A</div>
      <a class=\"result-link\" href=\"https://example.com/b\">Result B</a>
      <div class=\"result-snippet\">Snippet B</div>
    </body></html>
    """.strip()

    page_a = "<html><head><title>A Title</title></head><body><h1>A</h1><p>Hello A</p></body></html>"
    page_b = "<html><head><title>B Title</title></head><body><p>Hello B</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "lite.duckduckgo.com" in u:
            return httpx.Response(200, text=ddg_html)
        if u.startswith("https://example.com/a"):
            return httpx.Response(200, text=page_a)
        if u.startswith("https://example.com/b"):
            return httpx.Response(200, text=page_b)
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    _, _, news_search = make_http_tools(transport=transport)

    reg = ToolRegistry()
    reg.register_tool(news_search)

    transcript = Transcript(path=tmp_path / "t.jsonl")
    ctx = ToolContext(session_id="s", transcript=transcript, workspace_root=tmp_path)

    out = reg.call(
        "news_search",
        {"query": "x", "max_results": 2, "fetch_top_k": 2, "excerpt_chars": 200},
        ctx=ctx,
    )
    data = json.loads(out)
    assert data["query"] == "x"
    assert data["fetched_top_k"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["fetch"]["page_title"] == "A Title"
    assert "Hello A" in data["results"][0]["fetch"]["excerpt"]
