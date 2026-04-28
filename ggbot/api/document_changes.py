from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class TextRange:
    start: int
    end: int


def build_text_change_set(*, before: str, after: str) -> dict[str, object]:
    """Build a line-based change set for frontend diff rendering."""
    old_lines = before.splitlines(keepends=True)
    new_lines = after.splitlines(keepends=True)
    matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    ops: list[dict[str, object]] = []
    add_count = 0
    delete_count = 0
    replace_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "insert":
            op_type = "add"
            add_count += 1
        elif tag == "delete":
            op_type = "delete"
            delete_count += 1
        else:
            op_type = "replace"
            replace_count += 1

        ops.append(
            {
                "op": op_type,
                "old_range": TextRange(start=i1, end=i2).__dict__,
                "new_range": TextRange(start=j1, end=j2).__dict__,
                "old_text": "".join(old_lines[i1:i2]),
                "new_text": "".join(new_lines[j1:j2]),
            }
        )

    return {
        "version": "change_set@v1",
        "summary": {
            "total_ops": len(ops),
            "add_ops": add_count,
            "delete_ops": delete_count,
            "replace_ops": replace_count,
            "old_line_count": len(old_lines),
            "new_line_count": len(new_lines),
        },
        "ops": ops,
    }
