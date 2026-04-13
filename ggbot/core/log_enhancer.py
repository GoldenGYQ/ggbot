from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .types import ChatMessage


@dataclass
class LogFilter:
    """日志筛选器"""
    include_roles: Set[str] = None  # 包含的角色：system, user, assistant, tool, thinking
    exclude_roles: Set[str] = None  # 排除的角色
    include_types: Set[str] = None  # 包含的事件类型：model_message, tool_call, tool_result, etc.
    exclude_types: Set[str] = None  # 排除的事件类型
    min_length: int = 0  # 最小内容长度
    max_length: int = 0  # 最大内容长度（0表示无限制）
    search_text: str = ""  # 搜索文本
    time_range: Tuple[Optional[int], Optional[int]] = (None, None)  # 时间范围（毫秒时间戳）

    def __post_init__(self):
        if self.include_roles is None:
            self.include_roles = set()
        if self.exclude_roles is None:
            self.exclude_roles = set()
        if self.include_types is None:
            self.include_types = set()
        if self.exclude_types is None:
            self.exclude_types = set()


class LogEvent:
    """日志事件封装"""

    def __init__(self, event_data: Dict[str, Any]):
        self.ts_ms: int = event_data.get("ts_ms", 0)
        self.event_type: str = event_data.get("type", "")
        self.data: Dict[str, Any] = event_data.get("data", {})

        # 提取角色信息
        self.role: str = self.data.get("role", "")
        self.content: str = self.data.get("content", "")
        self.name: str = self.data.get("name", "")
        self.tool_calls: List[Dict] = self.data.get("tool_calls", [])

        # 大模型实际内容（原始输出）
        self.raw_content: str = self.data.get("raw_content", "")

    def matches_filter(self, filter_obj: LogFilter) -> bool:
        """检查事件是否匹配筛选条件"""

        # 角色筛选
        if filter_obj.include_roles and self.role not in filter_obj.include_roles:
            return False
        if filter_obj.exclude_roles and self.role in filter_obj.exclude_roles:
            return False

        # 事件类型筛选
        if filter_obj.include_types and self.event_type not in filter_obj.include_types:
            return False
        if filter_obj.exclude_types and self.event_type in filter_obj.exclude_types:
            return False

        # 内容长度筛选
        content_len = len(self.content) + len(self.raw_content)
        if content_len < filter_obj.min_length:
            return False
        if filter_obj.max_length > 0 and content_len > filter_obj.max_length:
            return False

        # 文本搜索
        if filter_obj.search_text:
            search_lower = filter_obj.search_text.lower()
            content_lower = (self.content + self.raw_content).lower()
            if search_lower not in content_lower:
                return False

        # 时间范围筛选
        start_time, end_time = filter_obj.time_range
        if start_time is not None and self.ts_ms < start_time:
            return False
        if end_time is not None and self.ts_ms > end_time:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ts_ms": self.ts_ms,
            "event_type": self.event_type,
            "role": self.role,
            "name": self.name,
            "content": self.content,
            "raw_content": self.raw_content,
            "tool_calls": self.tool_calls,
            "data": self.data
        }


class LogEnhancer:
    """日志增强器"""

    def __init__(self, transcript_path: Path):
        self.transcript_path = transcript_path
        self.events: List[LogEvent] = []
        self._load_events()

    def _load_events(self) -> None:
        """加载日志事件"""
        if not self.transcript_path.exists():
            return

        with self.transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event_data = json.loads(line)
                    self.events.append(LogEvent(event_data))
                except json.JSONDecodeError:
                    continue

    def filter_events(self, filter_obj: LogFilter) -> List[LogEvent]:
        """筛选事件"""
        return [event for event in self.events if event.matches_filter(filter_obj)]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_events": len(self.events),
            "by_type": {},
            "by_role": {},
            "time_range": None,
            "content_stats": {}
        }

        if not self.events:
            return stats

        # 按类型统计
        for event in self.events:
            stats["by_type"][event.event_type] = stats["by_type"].get(event.event_type, 0) + 1
            if event.role:
                stats["by_role"][event.role] = stats["by_role"].get(event.role, 0) + 1

        # 时间范围
        timestamps = [event.ts_ms for event in self.events if event.ts_ms > 0]
        if timestamps:
            stats["time_range"] = {
                "start": min(timestamps),
                "end": max(timestamps),
                "duration_ms": max(timestamps) - min(timestamps)
            }

        # 内容统计
        total_content_len = sum(len(event.content) + len(event.raw_content) for event in self.events)
        stats["content_stats"] = {
            "total_chars": total_content_len,
            "avg_chars_per_event": total_content_len // len(self.events) if self.events else 0
        }

        return stats

    def export_to_html(self, filter_obj: Optional[LogFilter] = None,
                      output_path: Optional[Path] = None) -> str:
        """导出为HTML"""
        filtered_events = self.filter_events(filter_obj) if filter_obj else self.events

        html = self._generate_html_header()
        html += self._generate_html_statistics(filtered_events)
        html += self._generate_html_events(filtered_events)
        html += self._generate_html_footer()

        if output_path:
            output_path.write_text(html, encoding="utf-8")

        return html

    def _generate_html_header(self) -> str:
        """生成HTML头部"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GGbot 日志查看器 - {self.transcript_path.name}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        .header {{
            border-bottom: 2px solid #4a90e2;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #2c3e50;
            margin: 0;
        }}
        .header .subtitle {{
            color: #7f8c8d;
            font-size: 14px;
            margin-top: 5px;
        }}
        .stats {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .stat-item {{
            background: white;
            padding: 10px;
            border-radius: 4px;
            border-left: 4px solid #4a90e2;
        }}
        .stat-label {{
            font-size: 12px;
            color: #7f8c8d;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .event {{
            margin-bottom: 20px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            overflow: hidden;
        }}
        .event-header {{
            padding: 10px 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }}
        .event-content {{
            padding: 15px;
            background: white;
        }}
        .event-raw {{
            padding: 15px;
            background: #f8f9fa;
            border-top: 1px dashed #e0e0e0;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .role-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .role-system {{ background: #e3f2fd; color: #1565c0; }}
        .role-user {{ background: #e8f5e9; color: #2e7d32; }}
        .role-assistant {{ background: #fff3e0; color: #ef6c00; }}
        .role-tool {{ background: #f3e5f5; color: #7b1fa2; }}
        .role-thinking {{ background: #fff8e1; color: #ff8f00; }}
        .timestamp {{
            color: #7f8c8d;
            font-family: 'Consolas', 'Monaco', monospace;
        }}
        .content-section {{
            margin-top: 10px;
        }}
        .content-label {{
            font-size: 11px;
            color: #7f8c8d;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .content-text {{
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            border: 1px solid #e9ecef;
        }}
        .tool-calls {{
            margin-top: 10px;
        }}
        .tool-call {{
            background: #e8f5e9;
            border: 1px solid #c8e6c9;
            border-radius: 4px;
            padding: 8px;
            margin-bottom: 5px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
        }}
        .filters {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .filter-section {{
            margin-bottom: 15px;
        }}
        .filter-label {{
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .filter-controls {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            background: #4a90e2;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        .filter-btn:hover {{
            background: #357ae8;
        }}
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>GGbot 日志查看器</h1>
            <div class="subtitle">
                文件: {self.transcript_path.name} |
                路径: {self.transcript_path}
            </div>
        </div>
"""

    def _generate_html_statistics(self, events: List[LogEvent]) -> str:
        """生成统计信息HTML"""
        if not events:
            return ""

        stats = self.get_statistics()
        filtered_count = len(events)

        return f"""
        <div class="stats">
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-label">总事件数</div>
                    <div class="stat-value">{stats['total_events']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">筛选后事件数</div>
                    <div class="stat-value">{filtered_count}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">总字符数</div>
                    <div class="stat-value">{stats['content_stats']['total_chars']:,}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">平均字符/事件</div>
                    <div class="stat-value">{stats['content_stats']['avg_chars_per_event']:,}</div>
                </div>
            </div>
        </div>
"""

    def _generate_html_events(self, events: List[LogEvent]) -> str:
        """生成事件列表HTML"""
        if not events:
            return '<div class="empty-state">没有找到匹配的事件</div>'

        html = ""
        for event in events:
            html += self._generate_html_event(event)

        return html

    def _generate_html_event(self, event: LogEvent) -> str:
        """生成单个事件HTML"""
        # 格式化时间戳
        dt = datetime.fromtimestamp(event.ts_ms / 1000)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # 角色徽章
        role_badge_class = f"role-{event.role}" if event.role else ""
        role_badge = f'<span class="role-badge {role_badge_class}">{event.role or event.event_type}</span>' if event.role or event.event_type else ""

        # 名称标签
        name_tag = f'<span style="margin-left: 10px; color: #666;">{event.name}</span>' if event.name else ""

        html = f"""
        <div class="event">
            <div class="event-header">
                <div>
                    {role_badge}
                    {name_tag}
                </div>
                <div class="timestamp">{time_str}</div>
            </div>
"""

        # 内容部分
        if event.content:
            html += f"""
            <div class="event-content">
                <div class="content-section">
                    <div class="content-label">内容</div>
                    <div class="content-text">{self._escape_html(event.content)}</div>
                </div>
"""

        # 大模型原始内容
        if event.raw_content:
            html += f"""
                <div class="content-section">
                    <div class="content-label">大模型原始输出</div>
                    <div class="content-text">{self._escape_html(event.raw_content)}</div>
                </div>
"""

        # 工具调用
        if event.tool_calls:
            html += """
                <div class="content-section">
                    <div class="content-label">工具调用</div>
                    <div class="tool-calls">
"""
            for tool_call in event.tool_calls:
                func = tool_call.get("function", {})
                html += f"""
                        <div class="tool-call">
                            {func.get('name', 'unknown')}({func.get('arguments', '')})
                        </div>
"""
            html += """
                    </div>
                </div>
"""

        html += """
            </div>
        </div>
"""
        return html

    def _generate_html_footer(self) -> str:
        """生成HTML页脚"""
        return """
    </div>
    <script>
        // 简单的筛选功能
        document.addEventListener('DOMContentLoaded', function() {
            // 这里可以添加JavaScript代码来实现动态筛选
            console.log('GGbot日志查看器已加载');
        });
    </script>
</body>
</html>
"""

    def _escape_html(self, text: str) -> str:
        """转义HTML特殊字符"""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;")
                   .replace("'", "&#39;")
                   .replace("\n", "<br>"))

    def extract_model_raw_content(self) -> List[Dict[str, Any]]:
        """提取大模型原始内容（用于调试和分析）"""
        raw_contents = []

        for event in self.events:
            if event.event_type == "model_message" and event.raw_content:
                raw_contents.append({
                    "ts_ms": event.ts_ms,
                    "role": event.role,
                    "raw_content": event.raw_content,
                    "parsed_content": event.content,
                    "tool_calls": event.tool_calls
                })

        return raw_contents