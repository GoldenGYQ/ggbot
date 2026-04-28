from pathlib import Path

import pytest

from ggbot.tools.docx_tools import make_docx_tools
from ggbot.tools.registry import ToolRegistry


def test_docx_tools_basic_flow(tmp_path: Path) -> None:
    pytest.importorskip("docx")
    tools = make_docx_tools(workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register_all(tools)

    create_out = registry.call("docx_create", {"path": "docs/a.docx", "title": "测试文档"})
    assert "已创建DOCX" in create_out

    registry.call("docx_add_heading", {"path": "docs/a.docx", "text": "第一章", "level": 1})
    registry.call("docx_add_paragraph", {"path": "docs/a.docx", "text": "这是正文"})
    outline = registry.call("docx_read_outline", {"path": "docs/a.docx", "max_items": 20})
    assert "第一章" in outline
    assert "这是正文" in outline

    save_out = registry.call("docx_save_as", {"source_path": "docs/a.docx", "target_path": "docs/b.docx"})
    assert "已另存为" in save_out
    assert (tmp_path / "docs" / "b.docx").exists()


def test_docx_tools_from_file_and_inline_limit(tmp_path: Path) -> None:
    pytest.importorskip("docx")
    tools = make_docx_tools(workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register_all(tools)

    registry.call("docx_create", {"path": "docs/a.docx"})
    text_file = tmp_path / "docs" / "content.txt"
    text_file.parent.mkdir(parents=True, exist_ok=True)
    text_file.write_text("这是一段来自文件的长文案。", encoding="utf-8")

    out = registry.call(
        "docx_add_paragraph_from_file",
        {"path": "docs/a.docx", "text_file_path": "docs/content.txt"},
    )
    assert "已从文件追加段落" in out

    long_text = "a" * 4500
    with pytest.raises(ValueError, match=r"\*_from_file"):
        registry.call("docx_add_paragraph", {"path": "docs/a.docx", "text": long_text})
