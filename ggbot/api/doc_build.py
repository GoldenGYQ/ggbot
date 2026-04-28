from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..workspace.permissions import ensure_under_root

_PLAN_BLOCK_RE = re.compile(r"```docx-plan\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
_SECTION_BLOCK_RE = re.compile(
    r"```docx-section(?P<header>[^\n]*)\n(?P<body>.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _parse_header_attrs(header: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r'([A-Za-z_][A-Za-z0-9_-]*)=("[^"]*"|[^\s]+)', header):
        key = match.group(1).strip()
        raw_value = match.group(2).strip()
        value = raw_value[1:-1] if raw_value.startswith('"') and raw_value.endswith('"') else raw_value
        attrs[key] = value
    return attrs


def _extract_plan(markdown_text: str) -> dict[str, Any]:
    plan_match = _PLAN_BLOCK_RE.search(markdown_text)
    if not plan_match:
        return {}
    raw = plan_match.group(1).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"docx-plan JSON 解析失败: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("docx-plan 必须是 JSON 对象")
    return parsed


def _extract_sections(markdown_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for match in _SECTION_BLOCK_RE.finditer(markdown_text):
        attrs = _parse_header_attrs(match.group("header") or "")
        body = (match.group("body") or "").strip()
        section_id = attrs.get("id") or f"section-{len(sections) + 1}"
        source_path = attrs.get("path") or f"docs/tmp/{section_id}.md"
        sections.append(
            {
                "id": section_id,
                "source_file": source_path,
                "content": body,
            }
        )
    return sections


def _build_steps(title: str, docx_path: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"step": "docx_create", "args": {"path": docx_path, "title": title}},
    ]
    for sec in sections:
        steps.append(
            {
                "step": "docx_add_heading",
                "args": {
                    "path": docx_path,
                    "text": sec.get("heading") or sec["id"],
                    "level": int(sec.get("level") or 1),
                },
            }
        )
        steps.append(
            {
                "step": "docx_add_paragraph_from_file",
                "args": {"path": docx_path, "text_file_path": sec["source_file"]},
            }
        )
    return steps


def _validate_manifest(manifest: dict[str, Any], section_contents: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    sections = manifest.get("sections") or []
    if not isinstance(sections, list):
        return ["sections 字段必须是数组"]

    levels: list[int] = []
    has_h1 = False
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        level = int(sec.get("level") or 1)
        levels.append(level)
        if level == 1:
            has_h1 = True
        sec_id = str(sec.get("id") or "")
        source = str(sec.get("source_file") or "")
        content = section_contents.get(sec_id, "")
        if not content.strip():
            warnings.append(f"章节 {sec_id or source} 内容为空")
        elif len(content.strip()) < 20:
            warnings.append(f"章节 {sec_id or source} 内容过短，建议补充")
    if not has_h1:
        warnings.append("缺少一级标题章节(level=1)")

    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 1:
            warnings.append(f"标题层级跳跃: {levels[i - 1]} -> {levels[i]}")
            break
    return warnings


def build_docx_manifest_from_markdown(
    *,
    markdown_text: str,
    workspace_root: Path,
    docs_dir: str = "docs",
    manifest_name: str = "doc_build_manifest.json",
    docx_path: str = "docs/output.docx",
    write_files: bool = True,
) -> dict[str, Any]:
    plan = _extract_plan(markdown_text)
    draft_sections = _extract_sections(markdown_text)
    if not draft_sections:
        raise ValueError("未找到 docx-section 块")

    plan_sections = plan.get("sections") if isinstance(plan.get("sections"), list) else []
    section_by_id = {str(sec["id"]): sec for sec in draft_sections}

    sections: list[dict[str, Any]] = []
    if plan_sections:
        for idx, sec in enumerate(plan_sections, start=1):
            if not isinstance(sec, dict):
                continue
            sec_id = str(sec.get("id") or f"section-{idx}")
            draft = section_by_id.get(sec_id, {})
            source_file = str(sec.get("source_file") or draft.get("source_file") or f"docs/tmp/{sec_id}.md")
            sections.append(
                {
                    "id": sec_id,
                    "heading": str(sec.get("heading") or sec_id),
                    "level": int(sec.get("level") or 1),
                    "source_file": source_file,
                    "constraints": sec.get("constraints") or {},
                }
            )
    else:
        for idx, sec in enumerate(draft_sections, start=1):
            sec_id = str(sec["id"])
            sections.append(
                {
                    "id": sec_id,
                    "heading": sec_id,
                    "level": 1 if idx == 1 else 2,
                    "source_file": str(sec["source_file"]),
                    "constraints": {},
                }
            )

    title = str(plan.get("title") or "Untitled Document")
    artifacts = [
        {"path": sec["source_file"], "type": "section_text", "status": "generated"}
        for sec in sections
    ]
    manifest: dict[str, Any] = {
        "schema_version": "doc_build@v1",
        "title": title,
        "sections": sections,
        "artifacts": artifacts,
        "build_steps": _build_steps(title=title, docx_path=docx_path, sections=sections),
    }

    section_contents: dict[str, str] = {}
    for sec in sections:
        sec_id = str(sec["id"])
        section_contents[sec_id] = str(section_by_id.get(sec_id, {}).get("content", ""))

    warnings = _validate_manifest(manifest, section_contents)
    manifest["quality_warnings"] = warnings

    docs_root = ensure_under_root(workspace_root, workspace_root / docs_dir)
    manifest_path = ensure_under_root(workspace_root, docs_root / manifest_name)

    if write_files:
        docs_root.mkdir(parents=True, exist_ok=True)
        for sec in sections:
            sec_id = str(sec["id"])
            text = section_contents.get(sec_id, "")
            target = ensure_under_root(workspace_root, workspace_root / str(sec["source_file"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "quality_warnings": warnings,
        "sections_written": len(sections),
        "write_files": write_files,
    }


def load_docx_manifest(*, workspace_root: Path, manifest_path: str) -> dict[str, Any]:
    target = ensure_under_root(workspace_root, workspace_root / manifest_path)
    if not target.exists():
        raise FileNotFoundError(f"docx 清单不存在: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"docx 清单 JSON 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("docx 清单必须是 JSON 对象")
    return data


def resolve_build_step_indexes(
    *,
    manifest: dict[str, Any],
    only_section_id: str | None = None,
    start_index: int = 0,
) -> list[int]:
    steps = manifest.get("build_steps")
    if not isinstance(steps, list):
        raise ValueError("docx 清单缺少 build_steps")
    total = len(steps)
    if total == 0:
        return []

    begin = max(0, int(start_index))
    if begin >= total:
        return []
    candidate_indexes = list(range(begin, total))
    if not only_section_id:
        return candidate_indexes

    sections = manifest.get("sections")
    if not isinstance(sections, list):
        raise ValueError("docx 清单缺少 sections")
    target = None
    for sec in sections:
        if isinstance(sec, dict) and str(sec.get("id")) == only_section_id:
            target = sec
            break
    if target is None:
        raise ValueError(f"未找到章节: {only_section_id}")

    heading = str(target.get("heading") or only_section_id)
    source_file = str(target.get("source_file") or "")
    matches: list[int] = []
    for idx in candidate_indexes:
        step = steps[idx] if idx < len(steps) else None
        if not isinstance(step, dict):
            continue
        args = step.get("args")
        if not isinstance(args, dict):
            continue
        if str(args.get("text") or "") == heading:
            matches.append(idx)
            continue
        if source_file and str(args.get("text_file_path") or "") == source_file:
            matches.append(idx)
    return matches


def default_state_path_from_manifest(manifest_path: str) -> str:
    base = Path(manifest_path)
    parent = base.parent if str(base.parent) else Path("docs")
    return str(parent / "doc_build_state.json")


def build_step_repair_suggestions(
    *,
    step_name: str,
    step_args: dict[str, Any],
    error: str,
) -> list[dict[str, Any]]:
    lower_error = error.lower()
    suggestions: list[dict[str, Any]] = []
    docx_path = str(step_args.get("path") or "")
    text_file_path = str(step_args.get("text_file_path") or "")

    if "docx不存在" in error or "not found" in lower_error:
        if docx_path:
            suggestions.append(
                {
                    "action": "create_docx_then_retry",
                    "tool": "docx_create",
                    "arguments": {"path": docx_path},
                    "reason": "目标 docx 不存在，先创建再重试当前步骤。",
                }
            )
    if "文本文件不存在" in error or "no such file" in lower_error:
        if text_file_path:
            suggestions.append(
                {
                    "action": "write_source_file_then_retry",
                    "tool": "file_write",
                    "arguments": {
                        "path": text_file_path,
                        "content": "# TODO: 补充该章节正文",
                    },
                    "reason": "章节源文件缺失，先补齐草稿文件再重跑。",
                }
            )
    if "headers 和 rows 不能同时为空" in error:
        suggestions.append(
            {
                "action": "fill_table_payload_then_retry",
                "tool": "docx_add_table",
                "arguments": {
                    **step_args,
                    "headers": ["列1", "列2"],
                    "rows": [["值1", "值2"]],
                },
                "reason": "表格参数为空，补全 headers/rows 后重试。",
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "action": "retry_current_step",
                "tool": step_name,
                "arguments": step_args,
                "reason": "可先原参数重试；若仍失败，检查路径权限与参数完整性。",
            }
        )
    return suggestions
