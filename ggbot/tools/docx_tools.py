from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..workspace.permissions import ensure_under_root
from .registry import tool

MAX_INLINE_TEXT_CHARS = 4000


def _require_docx():
    try:
        from docx import Document  # type: ignore
    except Exception as exc:
        raise RuntimeError("python-docx 未安装，请先安装: pip install python-docx") from exc
    return Document


def _resolve_docx_path(workspace_root: Path, relative_path: str) -> Path:
    return ensure_under_root(workspace_root, workspace_root / relative_path)


def _resolve_text_path(workspace_root: Path, relative_path: str) -> Path:
    return ensure_under_root(workspace_root, workspace_root / relative_path)


def _read_text_file(workspace_root: Path, relative_path: str) -> str:
    source = _resolve_text_path(workspace_root, relative_path)
    if not source.exists():
        raise FileNotFoundError(f"文本文件不存在: {source}")
    return source.read_text(encoding="utf-8")


def _validate_inline_text_length(field_name: str, text: str) -> None:
    if len(text) > MAX_INLINE_TEXT_CHARS:
        raise ValueError(
            f"{field_name} 长度为 {len(text)}，超过内联上限 {MAX_INLINE_TEXT_CHARS}。"
            "请先将内容写入文本文件，再使用 *_from_file 工具。"
        )


class DocxCreateArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    title: str | None = Field(default=None, description="可选文档标题")


class DocxAddParagraphArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    text: str = Field(..., description="段落文本")
    style: str | None = Field(default=None, description="段落样式名（可选）")


class DocxAddHeadingArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    text: str = Field(..., description="标题文本")
    level: int = Field(default=1, ge=0, le=9, description="标题级别（0-9）")


class DocxAddTableArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    headers: list[str] = Field(default_factory=list, description="表头")
    rows: list[list[str]] = Field(default_factory=list, description="数据行")


class DocxReplaceTextArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    old_text: str = Field(..., description="待替换文本")
    new_text: str = Field(..., description="替换后文本")


class DocxReadOutlineArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    max_items: int = Field(default=200, ge=1, le=1000, description="最大返回条目数")


class DocxSaveAsArgs(BaseModel):
    source_path: str = Field(..., description="源DOCX路径（相对workspace_root）")
    target_path: str = Field(..., description="目标DOCX路径（相对workspace_root）")


class DocxAddParagraphFromFileArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    text_file_path: str = Field(..., description="文本文件路径（相对workspace_root）")
    style: str | None = Field(default=None, description="段落样式名（可选）")


class DocxAddHeadingFromFileArgs(BaseModel):
    path: str = Field(..., description="DOCX文件路径（相对workspace_root）")
    text_file_path: str = Field(..., description="文本文件路径（相对workspace_root）")
    level: int = Field(default=1, ge=0, le=9, description="标题级别（0-9）")


def make_docx_tools(*, workspace_root: Path):
    @tool(name="docx_create", description="创建一个DOCX文档，可选写入标题。")
    def docx_create(args: DocxCreateArgs) -> str:
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        doc = Document()
        if args.title:
            doc.add_heading(args.title, level=0)
        doc.save(target)
        return f"已创建DOCX: {target}"

    @tool(name="docx_add_paragraph", description="向DOCX追加段落。")
    def docx_add_paragraph(args: DocxAddParagraphArgs) -> str:
        _validate_inline_text_length("text", args.text)
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        doc.add_paragraph(args.text, style=args.style)
        doc.save(target)
        return f"已追加段落到: {target}"

    @tool(
        name="docx_add_paragraph_from_file",
        description="从文本文件读取内容并向DOCX追加段落，适合长文案。",
    )
    def docx_add_paragraph_from_file(args: DocxAddParagraphFromFileArgs) -> str:
        text = _read_text_file(workspace_root, args.text_file_path)
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        doc.add_paragraph(text, style=args.style)
        doc.save(target)
        return f"已从文件追加段落到: {target}"

    @tool(name="docx_add_heading", description="向DOCX追加标题。")
    def docx_add_heading(args: DocxAddHeadingArgs) -> str:
        _validate_inline_text_length("text", args.text)
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        doc.add_heading(args.text, level=args.level)
        doc.save(target)
        return f"已追加标题到: {target}"

    @tool(
        name="docx_add_heading_from_file",
        description="从文本文件读取内容并向DOCX追加标题，适合长标题素材。",
    )
    def docx_add_heading_from_file(args: DocxAddHeadingFromFileArgs) -> str:
        text = _read_text_file(workspace_root, args.text_file_path)
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        doc.add_heading(text, level=args.level)
        doc.save(target)
        return f"已从文件追加标题到: {target}"

    @tool(name="docx_add_table", description="向DOCX追加表格。")
    def docx_add_table(args: DocxAddTableArgs) -> str:
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        if not args.headers and not args.rows:
            raise ValueError("headers 和 rows 不能同时为空")

        col_count = len(args.headers) if args.headers else len(args.rows[0])
        if col_count <= 0:
            raise ValueError("无法推断表格列数")

        doc = Document(target)
        table = doc.add_table(rows=1 if args.headers else 0, cols=col_count)
        if args.headers:
            for idx, header in enumerate(args.headers):
                table.rows[0].cells[idx].text = header
        for row_data in args.rows:
            row = table.add_row()
            for idx in range(col_count):
                row.cells[idx].text = row_data[idx] if idx < len(row_data) else ""
        doc.save(target)
        return f"已追加表格到: {target}"

    @tool(name="docx_replace_text", description="替换DOCX段落中的文本。")
    def docx_replace_text(args: DocxReplaceTextArgs) -> str:
        _validate_inline_text_length("old_text", args.old_text)
        _validate_inline_text_length("new_text", args.new_text)
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        replaced = 0
        for paragraph in doc.paragraphs:
            if args.old_text in paragraph.text:
                paragraph.text = paragraph.text.replace(args.old_text, args.new_text)
                replaced += 1
        doc.save(target)
        return f"已替换 {replaced} 个段落并保存: {target}"

    @tool(name="docx_read_outline", description="读取DOCX大纲（标题和前几段文本）。")
    def docx_read_outline(args: DocxReadOutlineArgs) -> dict[str, object]:
        Document = _require_docx()
        target = _resolve_docx_path(workspace_root, args.path)
        if not target.exists():
            raise FileNotFoundError(f"DOCX不存在: {target}")
        doc = Document(target)
        items: list[dict[str, str]] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style_name = str(getattr(para.style, "name", "") or "")
            item_type = "heading" if style_name.lower().startswith("heading") else "paragraph"
            items.append({"type": item_type, "style": style_name, "text": text})
            if len(items) >= args.max_items:
                break
        return {"path": str(target), "items": items, "count": len(items)}

    @tool(name="docx_save_as", description="复制DOCX到新文件。")
    def docx_save_as(args: DocxSaveAsArgs) -> str:
        Document = _require_docx()
        source = _resolve_docx_path(workspace_root, args.source_path)
        target = _resolve_docx_path(workspace_root, args.target_path)
        if not source.exists():
            raise FileNotFoundError(f"源DOCX不存在: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        doc = Document(source)
        doc.save(target)
        return f"已另存为: {target}"

    return (
        docx_create,
        docx_add_paragraph,
        docx_add_paragraph_from_file,
        docx_add_heading,
        docx_add_heading_from_file,
        docx_add_table,
        docx_replace_text,
        docx_read_outline,
        docx_save_as,
    )
