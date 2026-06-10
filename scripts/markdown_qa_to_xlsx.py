from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


QUESTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.*\S)\s*$")
ANSWER_MARKER_RE = re.compile(r"^\*\*答案[:：]?\*\*$|^答案[:：]?$")


@dataclass
class QAItem:
    index: int
    question: str
    answer: str


def parse_markdown_qa(markdown_path: Path) -> list[QAItem]:
    text = markdown_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    items: list[QAItem] = []
    current_index: int | None = None
    current_question: str | None = None
    current_answer_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_index, current_question, current_answer_lines
        if current_index is None or current_question is None:
            return

        answer_lines = current_answer_lines[:]
        while answer_lines and not answer_lines[0].strip():
            answer_lines.pop(0)
        if answer_lines and ANSWER_MARKER_RE.match(answer_lines[0].strip()):
            answer_lines.pop(0)
        while answer_lines and not answer_lines[0].strip():
            answer_lines.pop(0)
        while answer_lines and not answer_lines[-1].strip():
            answer_lines.pop()

        items.append(
            QAItem(
                index=current_index,
                question=current_question.strip(),
                answer="\n".join(answer_lines).strip(),
            )
        )
        current_index = None
        current_question = None
        current_answer_lines = []

    for line in lines:
        match = QUESTION_RE.match(line)
        if match:
            flush_current()
            current_index = int(match.group(1))
            current_question = match.group(2)
            current_answer_lines = []
            continue

        if current_index is not None:
            current_answer_lines.append(line)

    flush_current()
    return items


def excel_column_name(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def inline_cell(cell_ref: str, value: str, style_id: int) -> str:
    safe_value = escape(value).replace("\r\n", "\n").replace("\r", "\n")
    return (
        f'<c r="{cell_ref}" t="inlineStr" s="{style_id}">'
        f'<is><t xml:space="preserve">{safe_value}</t></is></c>'
    )


def build_sheet_xml(items: list[QAItem]) -> str:
    rows = [("序号", "问题", "答案")]
    rows.extend((str(item.index), item.question, item.answer) for item in items)

    xml_rows: list[str] = []
    for row_idx, row in enumerate(rows, start=1):
        style_id = 2 if row_idx == 1 else 1
        cells = []
        for col_idx, value in enumerate(row, start=1):
            cell_ref = f"{excel_column_name(col_idx)}{row_idx}"
            cells.append(inline_cell(cell_ref, value, style_id))
        xml_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    last_row = len(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:C{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        '<cols>'
        '<col min="1" max="1" width="10" customWidth="1"/>'
        '<col min="2" max="2" width="48" customWidth="1"/>'
        '<col min="3" max="3" width="120" customWidth="1"/>'
        '</cols>'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        '<autoFilter ref="A1:C1"/>'
        '</worksheet>'
    )


def build_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
    <font>
      <b/>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">
      <alignment vertical="top" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">
      <alignment vertical="top" wrapText="1"/>
    </xf>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""


def build_workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="问答" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""


def build_workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
                Target="styles.xml"/>
</Relationships>
"""


def build_root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                Target="xl/workbook.xml"/>
  <Relationship Id="rId2"
                Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
                Target="docProps/core.xml"/>
  <Relationship Id="rId3"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
                Target="docProps/app.xml"/>
</Relationships>
"""


def build_content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml"
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml"
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml"
            ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml"
            ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


def build_app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>markdown_qa_to_xlsx.py</Application>
</Properties>
"""


def build_core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>问答导出</dc:title>
  <dc:creator>markdown_qa_to_xlsx.py</dc:creator>
  <cp:lastModifiedBy>markdown_qa_to_xlsx.py</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""


def write_xlsx(output_path: Path, items: list[QAItem]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", build_content_types_xml())
        zf.writestr("_rels/.rels", build_root_rels_xml())
        zf.writestr("docProps/app.xml", build_app_xml())
        zf.writestr("docProps/core.xml", build_core_xml())
        zf.writestr("xl/workbook.xml", build_workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", build_workbook_rels_xml())
        zf.writestr("xl/styles.xml", build_styles_xml())
        zf.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(items))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将标准问答 Markdown 转成 Excel 文件。")
    parser.add_argument("input_md", type=Path, help="输入的 Markdown 文件路径")
    parser.add_argument("output_xlsx", type=Path, nargs="?", help="输出的 xlsx 文件路径")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_md: Path = args.input_md
    output_xlsx: Path = args.output_xlsx or input_md.with_suffix(".xlsx")

    if not input_md.exists():
        parser.error(f"输入文件不存在: {input_md}")

    items = parse_markdown_qa(input_md)
    if not items:
        parser.error("没有在 Markdown 中解析到任何问答条目，请检查格式是否为 `## 序号. 问题`。")

    write_xlsx(output_xlsx, items)
    print(f"已生成 Excel: {output_xlsx}")
    print(f"共导出 {len(items)} 条问答。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
