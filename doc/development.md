# 开发指南（Development）

**文档分级：A（只给项目成员｜内部）**

## 环境要求

- Python 3.10+
- Windows/macOS/Linux 均可
- 推荐使用 `uv` 管理虚拟环境与依赖（仓库已包含 `uv.lock`）

## 安装与运行（uv）

从仓库根目录：

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv sync --extra dev
```

常用命令：

- `uv run ggbot --help`
- `uv run ggbot repl`
- `uv run ggbot chat "hello"`
- `uv run ggbot tui`
- `uv run ggbot log --follow --events`

## 开发调试

- 更友好的 traceback：`uv run ggbot --debug repl`
- 定位测试失败：
  - `uv run pytest -k query_loop -vv`
  - `uv run pytest --lf -vv`
  - `uv run pytest --pdb`

## 常改动点

### 1) 新增一个工具（tool）

建议步骤：

1) 在 `ggbot/tools/` 下新增模块（或在现有模块中新增）
2) 用 `@tool()` 装饰器声明 schema
3) 在 `ggbot/cli.py` 的 `_register_builtin_tools()` 里注册
4) 在 `tests/` 下补单测（无外部依赖；网络用 mock）

工具签名两种写法：

- 无上下文：`def my_tool(args: MyArgs) -> str`
- 带上下文：`def my_tool(ctx: ToolContext, args: MyArgs) -> str`

### 2) 改 query loop（高风险）

`ggbot/core/agent_loop.py` 里涉及：
- message 顺序合法性（tool_calls 紧跟 tool messages）
- transcript 事件顺序
- budget 防失控

改动原则：
- 先加/改测试，再改实现
- 不要破坏旧 transcript JSONL 的可恢复性

### 3) 改 provider（LiteLLM）

provider 实现位于：`ggbot/providers/litellm_client.py`

建议：
- 对 LiteLLM 的流式 chunk 合并逻辑写针对性测试（见 `tests/test_litellm_streaming.py`）
- provider 抛出的异常需要统一包装为 `ProviderError`，避免 query loop 里出现 provider-specific 异常

## 代码风格与约定

- 保持 `from __future__ import annotations` 风格一致
- 类型提示：优先让 Pylance 能静态检查通过
- 工具输入：使用 Pydantic `BaseModel`（schema 与校验统一）
- 工具输出：尽量是短文本；超长输出应截断（避免污染上下文和 transcript）

## 文档维护

- 本仓库 `doc/` 默认 A 级内部文档。
- 新增/修改行为必须同步更新：
  - `README.md`（快速开始/配置）
  - 对应 `doc/*.md`
  - `tests/`（行为变化必须有测试）
