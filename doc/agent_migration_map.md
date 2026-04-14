# GGbot 通用 Agent 迁移映射

**文档分级：A（只给项目成员｜内部）**

这份文档的目标不是重写现有代码，而是把 GGbot 逐步演进为一个“可二次开发、可替换交互壳、可替换 transport、可插件化扩展”的通用 agent runtime。

## 设计目标

1. 核心业务和外部接入解耦。
2. 事件协议稳定，UI 和 transport 只做适配。
3. transcript 成为唯一事实源。
4. 工具、provider、存储、配置都通过接口替换。
5. 后续新增 Web/React/CLI/TUI/stdio/WebSocket/HTTP 时不破坏核心结构。

## 推荐目标结构

```text
agent/
  core/            # 会话、状态机、消息流、预算、权限、调度
  domain/          # Message、ToolCall、ToolResult、SessionState 等领域模型
  runtime/         # query loop、生命周期、事件总线、执行协调
  transports/      # stdio / websocket / http / sse
  ui/              # CLI / TUI / Web 适配层
  tools/           # 工具接口 + 内置工具
  plugins/         # 第三方插件
  storage/         # transcript / session / cache / index
  providers/       # LLM / ASR / TTS / embedding
  config/          # 配置加载与校验
  observability/   # 日志、指标、trace、审计
  cli.py
```

## 当前代码到目标架构的映射

| 当前模块 | 当前职责 | 目标层 | 迁移建议 |
|---|---|---|---|
| `ggbot/core/agent_loop.py` | 主循环、tool call 执行、预算、thinking 解析、provider 交互 | `runtime/` + `core/` | 拆成 runtime 编排和纯业务状态机；thinking 解析保留在 domain/adapter 边界 |
| `ggbot/core/transcript.py` | JSONL 事件写入、事件回放、session 文件定位 | `storage/` | 保留为事实源；扩展为统一事件存储接口，不让 UI 直接写文件 |
| `ggbot/core/session_meta.py` | session 标题、用户轮次等元信息 | `storage/` | 保留，但改成 session store 的一部分 |
| `ggbot/core/sessions.py` | 默认会话 id、会话目录 | `storage/` / `runtime/` | 作为 session 发现与初始化工具 |
| `ggbot/core/config.py` | 环境变量、TOML、默认值加载 | `config/` | 保持独立；配置只向外暴露已解析结果 |
| `ggbot/core/permissions.py` | workspace 与 shell 安全边界 | `core/` | 作为安全域能力保留，不能被 UI 绕过 |
| `ggbot/providers/litellm_client.py` | 多 provider 统一调用、stream collect | `providers/` | 保持 provider adapter，未来可替换为 OpenAI/Anthropic/本地模型适配层 |
| `ggbot/tools/registry.py` | 工具注册、schema 导出、执行 | `tools/` | 保留为工具插件入口；执行器与 schema 仍然是核心扩展点 |
| `ggbot/tools/context.py` | tool 的运行时上下文、事件发射 | `runtime/` + `tools/` | 维持注入式上下文，不让工具直接依赖全局对象 |
| `ggbot/tools/*.py` | 文件、shell、HTTP、jobs、workspace、status 等工具 | `tools/` | 逐步插件化；工具逻辑与 transport/UI 解耦 |
| `ggbot/prompts/*` | PromptProfile / PromptBuilder / PromptRepository | `core/` 或 `config/` | 保持独立模板层，核心只接收渲染后的 system prompt |
| `ggbot/ui/tui.py` | Textual TUI、快捷键、交互、状态栏 | `ui/` | 只消费事件，不直接处理业务分支 |
| `ggbot/cli.py` | CLI 命令入口、模式启动、log viewer | `ui/` + `runtime/` | CLI 只负责启动 runtime 和渲染事件 |
| `ggbot/providers/types.py` / `ggbot/core/types.py` | 消息、tool、session 类型 | `domain/` | 统一抽成领域模型，避免类型散落各层 |

## 现在最该先抽的边界

### 1. 领域模型边界

把以下概念固定下来，并让各层都复用同一套定义：

- `Message`
- `ToolCall`
- `ToolResult`
- `SessionState`
- `RuntimeEvent`
- `TransportEvent`
- `PermissionDecision`

### 2. 事件协议边界

建议统一使用以下事件族：

- `request`
- `response`
- `event`
- `status`
- `error`
- `tool_call`
- `tool_result`
- `assistant_delta`
- `assistant_final`
- `thinking`
- `turn_update`

### 3. transport 边界

把 `stdio / websocket / http / sse` 都收敛成同一接口：

- `connect()`
- `send()`
- `on_message()`
- `close()`
- `reconnect()`

这样后续替换 transport 时，核心 runtime 不需要改。

## 迁移顺序建议

### Phase 1: 先固化协议

1. 抽出稳定事件 schema。
2. 把 transcript 作为唯一事实源。
3. 让所有 UI 只消费事件。

### Phase 2: 再拆 runtime

1. 把 `run_query` 拆成独立 runtime。
2. 把 provider、tool execution、budget、thinking extraction 拆开。
3. 让 runtime 不依赖任何特定 UI。

### Phase 3: 再抽 transport

1. 先实现 `stdio` 版本。
2. 再加 `WebSocket`。
3. 如果需要服务化，再加 `HTTP + SSE`。

### Phase 4: 再插件化工具和 UI

1. 工具通过 registry/plugin 注册。
2. UI 通过 event bus 订阅事件。
3. 不让工具、UI、transport 互相直连。

## 现在仓库里最容易破坏架构的点

1. `cli.py` 同时承担启动、渲染、日志、会话恢复等职责，容易变成“上帝入口”。
2. `agent_loop.py` 既做状态机，又做 thinking 解析、预算、修复、执行，未来需要拆分。
3. `tools` 当前是集中注册制，适合继续演进为 plugin registry，但不要让工具回头耦合 UI。
4. `transcript` 是最重要的稳定层，不能被简化成普通 debug log。

## 结论

GGbot 要演进成通用 agent，最优路线不是“换一个 UI 框架”，而是：

- 先稳住事件协议
- 再抽 runtime
- 再统一 transport
- 最后插件化 UI / tools / providers

只要这条线守住，后续二次开发就不会把代码结构打散。