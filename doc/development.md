# 开发指南（Development）

**文档分级：A（只给项目成员｜内部）**

## 环境要求

- Python 3.10+
- Windows / macOS / Linux
- 推荐使用 `uv`（仓库内含 `uv.lock`）

## 安装与运行

在仓库根目录执行：

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --extra dev
```

常用命令：

- `uv run ggbot --help`
- `uv run ggbot repl`
- `uv run ggbot tui`
- `uv run ggbot api --host 127.0.0.1 --port 8000`
- `uv run ggbot log --follow --events`

## 关键代码路径（当前真实）

- CLI 入口：`ggbot/command.py`
- API 入口：`ggbot/api/server.py`
- 服务层：`ggbot/api/services.py`
- 会话隔离：`ggbot/api/session_runtime_manager.py`
- 主循环：`ggbot/runtime/agent_loop.py`
- 工具执行：`ggbot/runtime/tool_execution.py`
- transcript：`ggbot/state/transcript.py`
- 工具注册：`ggbot/tools/manager.py`、`ggbot/tools/registry.py`

## 高频改动场景

### 1) 新增工具（Tool）

推荐步骤：

1. 在 `ggbot/tools/` 新增或扩展模块
2. 用 `@tool()` 声明 schema
3. 在 `ggbot/tools/manager.py` 注册
4. 在 `tests/` 增加针对性测试（外部依赖必须 mock）

常见签名：

- `def my_tool(args: MyArgs) -> str`
- `def my_tool(ctx: ToolContext, args: MyArgs) -> str`

### 2) 修改主循环（高风险）

涉及文件：`ggbot/runtime/agent_loop.py`。

重点检查：

- tool call / tool result 顺序合法性
- `RuntimeEvent` 发射时机是否稳定
- transcript 落盘顺序是否可回放
- turn/tool budget 是否仍可控

原则：

- 先补测试，再改实现
- 不破坏历史 transcript 的可恢复性

### 3) 修改 API 行为（高风险）

涉及文件：`ggbot/api/server.py`、`ggbot/api/services.py`。

重点检查：

- REST/WS 返回结构兼容性
- 会话隔离（`session_id` 与 `connection_id` 绑定）
- 实时事件是否仍“连接级投递”而非全局广播
- 权限审批链路（`permission_request/permission_response`）是否闭环

## 调试与测试

- 快速回归：`uv run pytest -q`
- 定位某类失败：`uv run pytest -k api -vv`
- 最近失败重跑：`uv run pytest --lf -vv`
- 调试模式：`uv run ggbot --debug repl`

## 开发约定

- 默认使用类型标注，优先保证编辑器静态检查可读
- 工具输入优先 `Pydantic BaseModel`
- 工具输出优先短文本，避免超长内容污染上下文
- 事件新增/变更必须同步更新：
  - `doc/API_README.md`
  - 相关消费端（TUI/Web/API）
  - 回归测试

## 文档联动

行为变化至少同步更新三处：

- `README.md`（对外入口）
- 对应 `doc/*.md`
- `tests/`（可验证变化）
