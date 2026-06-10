"""Tests for DOCX creation, editing, table operations, and style updates."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from ggbot.tools.docx_tools import make_docx_tools
from ggbot.tools.registry import ToolRegistry


def _as_dict(value):
    if isinstance(value, dict):
        return value
    return json.loads(value)


@pytest.mark.unit
def test_docx_tools_basic_flow(tmp_path: Path) -> None:
    """A basic create -> add heading -> add paragraph -> read outline -> save-as flow should succeed."""
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
    check_out = registry.call(
        "docx_build_check",
        {"path": "docs/a.docx", "expected_headings": ["第一章"], "min_paragraph_chars": 2},
    )
    assert "warnings" in check_out
    assert "stats" in check_out

    save_out = registry.call("docx_save_as", {"source_path": "docs/a.docx", "target_path": "docs/b.docx"})
    assert "已另存为" in save_out
    assert (tmp_path / "docs" / "b.docx").exists()


@pytest.mark.unit
def test_docx_tools_from_file_and_inline_limit(tmp_path: Path) -> None:
    """Text from a file can be appended; inline text over 4000 chars should be rejected."""
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


@pytest.mark.unit
def test_docx_tools_inspect_and_table_style_update(tmp_path: Path) -> None:
    """Tables can be created, inspected, and their styles updated."""
    pytest.importorskip("docx")
    tools = make_docx_tools(workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register_all(tools)

    registry.call("docx_create", {"path": "docs/t.docx", "title": "表格样式测试"})
    registry.call(
        "docx_add_table",
        {
            "path": "docs/t.docx",
            "headers": ["姓名", "分数"],
            "rows": [["张三", "95"], ["李四", "88"]],
        },
    )

    structure = _as_dict(registry.call("docx_inspect_structure", {"path": "docs/t.docx"}))
    assert structure["table_count"] == 1
    assert any(item.get("type") == "table" for item in structure["nodes"])

    styles = _as_dict(registry.call("docx_list_styles", {"path": "docs/t.docx"}))
    assert isinstance(styles["table_styles"], list)
    assert len(styles["table_styles"]) > 0

    read_out = _as_dict(registry.call("docx_read_table", {"path": "docs/t.docx", "table_index": 0}))
    assert read_out["row_count"] == 3
    assert read_out["rows"][0][0] == "姓名"

    target_style = "Table Grid" if "Table Grid" in styles["table_styles"] else styles["table_styles"][0]
    update_out = registry.call(
        "docx_update_table_style",
        {
            "path": "docs/t.docx",
            "table_index": 0,
            "style": target_style,
            "alignment": "center",
            "autofit": True,
        },
    )
    assert "已更新表格样式" in update_out

    read_after = _as_dict(registry.call("docx_read_table", {"path": "docs/t.docx", "table_index": 0}))
    assert read_after["style"]


@pytest.mark.unit
def test_docx_tools_update_cell_style_and_replace_in_table(tmp_path: Path) -> None:
    """Individual cell styles can be updated and text can be replaced in table cells."""
    pytest.importorskip("docx")
    tools = make_docx_tools(workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register_all(tools)

    registry.call("docx_create", {"path": "docs/cell.docx", "title": "单元格操作测试"})
    registry.call(
        "docx_add_table",
        {
            "path": "docs/cell.docx",
            "headers": ["项目", "状态"],
            "rows": [["任务A", "pending"], ["任务B", "pending"]],
        },
    )

    style_out = registry.call(
        "docx_update_cell_style",
        {
            "path": "docs/cell.docx",
            "table_index": 0,
            "row_start": 1,
            "row_end": 2,
            "col_start": 1,
            "col_end": 1,
            "bold": True,
            "text_align": "center",
            "vertical_align": "center",
        },
    )
    assert "已更新单元格样式" in style_out

    replace_out = registry.call(
        "docx_replace_in_table",
        {
            "path": "docs/cell.docx",
            "table_index": 0,
            "old_text": "pending",
            "new_text": "done",
            "row_start": 1,
            "row_end": 2,
            "columns": [1],
        },
    )
    assert "已在表格中替换文本" in replace_out

    read_out = _as_dict(registry.call("docx_read_table", {"path": "docs/cell.docx", "table_index": 0}))
    assert read_out["rows"][1][1] == "done"
    assert read_out["rows"][2][1] == "done"

