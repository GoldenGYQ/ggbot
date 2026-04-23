# 架构（Architecture）



文档分级：A（只给项目成员｜内部）



## 文档目的

本文档描述   当前仓库已落地实现  （非目标态），用于：

- 新成员快速建立系统心智模型
- 评估改动影响范围（API / runtime / tools / transcript）
- 统一安全、性能、重构讨论语义

相关文档：

- 安全现状与风险：`doc/security.md`
- 认证与传输分层计划：`doc/user_auth_and_transport_split_plan.md`
- 当前问题清单：`doc/当前问题.md`

## 事实基线（避免路径误判）

- 仓库根目录：`<repo>/`
- Python 包实际根目录：`<repo>/ggbot/`
- 本文中如写 `api/server.py`，默认指 `ggbot/api/server.py`

## 当前目录与职责（以代码为准）

```text
ggbot/
  __main__.py                    # python -m ggbot 入口
  command.py                     # Typer CLI 入口（chat/repl/tui/log/api）

  app/
    config.py                    # 配置加载（~/.ggbot/.env + ~/.ggbot/config.toml）
    app_bootstrap.py             # AppSession / AgentRuntime 创建与会话切换
    client_factory.py            # LLM client 工厂

  api/
    server.py                    # FastAPI + WS 路由、连接管理、命令分发
    services.py                  # 会话、消息、工具、配置、权限响应等服务
    permission_manager.py        # shell 权限请求/响应协调（阻塞等待）
    session_runtime_manager.py   # API 模式多会话上下文缓存与会话锁

  runtime/
    agent_loop.py                # run_query 主循环（turn + tool budget）
    model_interaction.py         # provider 流式交互、thinking/plan 解析
    tool_execution.py            # 工具调用、tool_call/tool_result 事件落盘
    history_repair.py            # tool message 历史修复

  state/
    transcript.py                # transcript 读写、open_session、消息回放
    session_store.py             # sessions.json 元数据
    sessions.py                  # 默认会话发现（chat/repl/tui）
    session_meta.py              # 会话元信息模型

  events/
    event_bus.py                 # 全局事件总线（发布/订阅）
    runtime_events.py            # runtime event 构造与消费分发
    event_mappings.py            # domain event -> transcript event 映射
    transcript_logger.py         # 兼容/辅助链路：订阅 event_bus 并写 transcript
    event_handlers/*             # 事件处理器（TUI/监控适配）

  tools/
    manager.py                   # 内置工具装配
    registry.py                  # 工具注册、schema、调用入口
    context.py                   # ToolContext（session/transcript/workspace）
    file_tools.py / shell_*.py / http_tools.py / web.py / jobs_tool.py ...

  providers/
    litellm_client.py            # LLM provider 适配
    types.py                     # ChatCompletionClient 协议

  prompts/
    manager.py / builder.py / repository.py / types.py

  transport/
    transcript_contract.py       # transcript 事件契约
    transport_protocol.py        # envelope 编解码（当前 API 未全面接入）

  ui/
    renderers/tui_renderer.py    # TUI 事件渲染适配

  workspace/
    permissions.py               # 工作区路径约束
    workspace_manager.py         # 允许工作区管理（~/.ggbot/allowed_workspaces.json）
```

## 系统架构框图（真实实现）

```mermaid
flowchart TB
    subgraph L1["接入层"]
        UI["用户交互入口<br/>CLI / TUI / Web 前端"]
        SERVER["API 接入与协议分发<br/>api/server.py"]
    end

    subgraph L2["编排层"]
        BOOT["运行时装配与启动<br/>app/app_bootstrap.py"]
        SVC["会话/消息/工具服务编排<br/>api/services.py"]
        SRM["按会话隔离执行上下文与锁<br/>api/session_runtime_manager.py"]
    end

    subgraph L3["执行层"]
        LOOP["Agent 主循环（turn/tool budget）<br/>runtime/agent_loop.py"]
        MODEL["模型交互与流式事件解析<br/>runtime/model_interaction.py"]
        TOOLS["工具注册与调用网关<br/>tools/registry.py"]
        PERM["权限审批协调（阻塞等待/唤醒）<br/>api/permission_manager.py"]
    end

    subgraph L4["存储与基础设施层"]
        PROVIDER["LLM Provider 适配（LiteLLM）<br/>providers/litellm_client.py"]
        TRANS["会话事实日志（jsonl）<br/>state/transcript.py"]
        STORE["会话元数据存储（sessions.json）<br/>state/session_store.py"]
        CFG["配置加载与覆盖规则<br/>app/config.py"]
        BUS["全局事件总线（辅助/fallback）<br/>events/event_bus.py"]
    end

    UI --> SERVER
    SERVER --> SVC
    SERVER --> BOOT
    BOOT --> CFG
    SVC --> SRM
    SVC --> STORE
    SVC --> PERM

    SRM --> LOOP
    LOOP --> MODEL
    MODEL --> PROVIDER
    LOOP --> TOOLS
    LOOP --> TRANS
    TOOLS --> PERM
    PERM -. fallback .-> BUS
```

> 为保证图面清晰，`history_repair.py`、`transcript_logger.py`、`ToolContext` 等辅助模块未单独展开，保留在文字说明中。

## API 模式逻辑框图（当前）

```mermaid
flowchart TB
    subgraph A["客户端"]
        FE["Vue / 其他客户端"]
    end

    subgraph B["接入层"]
        WS["/ws command"]
        SERVER["APIServer"]
    end

    subgraph C["服务与执行层"]
        SVC["APIService"]
        SRM["SessionRuntimeManager"]
        LOOP["run_query"]
        TOOL["ToolRegistry"]
        PM["PermissionManager"]
    end

    subgraph D["基础设施"]
        MODEL["Provider Client"]
        TRANS["Transcript"]
        STORE["SessionStore"]
        CFG["Settings"]
        BUS["EventBus fallback"]
    end

    FE --> WS
    WS --> SERVER
    SERVER --> SVC
    SVC --> SRM
    SRM --> LOOP
    SVC --> LOOP
    SVC --> TOOL
    SVC --> STORE
    SVC --> CFG
    LOOP --> MODEL
    LOOP --> TRANS
    LOOP --> TOOL
    TOOL --> PM
    PM -. no request context .-> BUS
```

## 启动与运行路径

### 1) CLI 模式

1. `python -m ggbot` -> `ggbot/__main__.py` -> `command.app()`
2. `chat/repl` 通过 `create_app_session()` + `create_agent_bootstrap()` 初始化运行时
3. 调用 `run_query()` 执行一轮对话
4. transcript 直接由 runtime 写入；CLI 通过返回事件做终端渲染

### 2) API 模式（当前前后端主链路）

1. `ggbot api --host --port` 进入 `command.py:api`
2. 创建 `AgentRuntime` 后启动 `run_api_server()`
3. `api/server.py` 暴露 REST + WS；消息主链路是 WS `send_message`
4. `api/services.py` 调用 `run_query`、`registry.call`、`session_store`
5. 事件通过 WS 回推客户端，transcript 同步落盘

> 注意：`/api/v1/messages` 和 `/api/v1/permissions/respond` 在 `server.py` 中已标注弃用并注释保留，当前建议统一走 WS 命令。

## 核心对象关系

### AgentRuntime（`app/app_bootstrap.py`）

`AgentRuntime` 持有核心可变状态：

- `session_id`
- `transcript`
- `messages`
- `registry`
- `client`
- `system_message`

`switch_runtime_session()` 会替换 `session_id/transcript/messages`，是低层会话切换能力；
API 主链路当前优先通过 `SessionRuntimeManager` 管理会话上下文，不直接改写共享 `runtime` 状态。

### APIService（`api/services.py`）

服务层能力：

- 会话列表/创建/查询/更新/删除/切换
- 会话上下文隔离：通过 `SessionRuntimeManager` 按 `session_id` 缓存 `transcript/messages` 与 session lock
- `send_message`（线程池中调用 `run_query`）
- `execute_tool`（线程池中调用 `registry.call`）
- `respond_permission`（对接 `PermissionManager.resolve`）
- 配置查询与更新、最近事件缓冲查询

### PermissionManager（`api/permission_manager.py`）

- `request()`：创建待审批请求并阻塞等待
- `resolve()`：校验连接/会话归属后唤醒等待方
- 事件发射策略：
  - 优先写入当前请求的 `transcript` 并走当前请求 `event_callback`（WS 连接级）
  - 只有缺失请求上下文时才 fallback 到全局 `event_bus`

## 信令流图（时序）

### 1) WS 消息类型与生命周期

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant WS as APIServer

    FE->>WS: type=command
    alt 命令执行成功
        WS-->>FE: type=response
    else 命令执行失败
        WS-->>FE: type=error
    end
```

### 2) 单轮对话（含工具调用）信令

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant WS as APIServer_WS
    participant SVC as APIService
    participant QRY as run_query
    participant CORE as Model_Tools_Transcript

    FE->>WS: send_message
    WS->>SVC: send_message
    SVC->>QRY: 启动 run_query
    QRY->>CORE: 执行模型轮次/工具调用/落盘

    loop 运行中事件
        QRY-->>SVC: runtime event
        SVC-->>WS: event_callback
        WS-->>FE: type=event
    end

    QRY-->>SVC: 返回 QueryResult
    SVC-->>WS: 返回 final payload
    WS-->>FE: type=response
```

### 3) Shell 权限审批信令（API 模式）

```mermaid
sequenceDiagram
    participant RT as Tool runtime
    participant PM as PermissionManager
    participant SVC as APIService callback/event
    participant WS as APIServer
    participant FE as Frontend

    RT->>PM: 发起审批请求
    PM->>SVC: emit permission_request
    SVC-->>WS: event_callback
    WS-->>FE: 推送审批事件
    FE->>WS: 提交审批结果
    WS->>PM: 调用 resolve
    PM-->>RT: 唤醒等待线程
    PM->>SVC: emit permission_response
    PM-->>RT: 返回审批结果
    SVC-->>WS: event_callback
    WS-->>FE: 推送审批结果事件
```

### 4) 会话切换信令（API 模式）

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant WS as APIServer/WS
    participant SVC as APIService
    participant SRM as SessionRuntimeManager
    participant SS as SessionStore
    participant TS as Transcript

    FE->>WS: switch_session
    WS->>SVC: switch_session(session_id)
    SVC->>SS: ensure_saved(old_session)
    SVC->>SRM: get_or_create_context(session_id)
    SRM->>TS: 打开 transcript 并加载 messages
    SVC->>SS: ensure_saved(new_session)
    SVC-->>WS: 返回 current_session_id 和 session
    WS-->>FE: type=response
```

## 事件与持久化模型（当前真实路径）

### A. 对话执行事件（主链路）

- 来源：`run_query` / `perform_model_turn` / `execute_tool_call`
- 形态：函数内构造 `RuntimeEvent`，通过 `event_callback` 传给 APIService/WS
- 持久化：runtime 直接 `transcript.append(...)`，不是先发 event bus 再落盘

### B. 全局事件总线事件（辅助链路）

- 来源：无请求上下文时的 `permission_manager` fallback、部分 `ui/event_handlers`
- 形态：`publish_event(...)` 到 `events/event_bus.py`
- 消费：兼容/离线上下文场景的辅助通知链路
- 现状：API 主链路（`send_message`）不依赖全局总线做 WS 事件推送

### Transcript（事实源）

持久化文件：

- 会话事件：`<transcript_dir>/<session_id>.jsonl`
- 元数据：`<transcript_dir>/sessions.json`（由 `SessionStore` 维护）

常见 transcript 事件类型：

- `model_message`
- `tool_call`
- `tool_result`
- `thinking`
- `turn_info` / `turn_update` / `turn_complete`
- `status`
- `provider_error`

## 工具系统

- `tools/manager.py` 负责创建并注册内置工具
- `tools/registry.py` 提供工具 schema 与统一调用入口
- `ToolContext` 注入 `session_id/transcript/workspace_root`
- 工具预算由 `runtime/agent_loop.py` 中 `ToolLimits` + `_ToolBudgetState` 控制
- `shell_run` 在 API 模式默认通过 `shell_confirm_callback` 接入权限审批流程

## 传输协议层（现状）

`transport/transport_protocol.py` 已定义标准 envelope：

- `version`
- `session_id`
- `seq`
- `ts_ms`
- `source`
- `event_type`
- `data`

但当前 `api/server.py` 的 WS 推送仍使用自定义结构（`type/event_type/data/timestamp/source`），尚未全量切换到 envelope。

## 当前架构约束（必须知晓）

以下是当前实现事实，不是目标态：

- API 模式使用全局 `runtime/APIService`，仍是单进程共享可变状态
- API 的多会话执行上下文已由 `SessionRuntimeManager` 隔离；但仍是单进程内存态，不跨进程共享
- WS 事件主链路是请求级 `event_callback` 定向回推，不再默认依赖全局总线订阅
- 消息主链路已转 WS；部分旧 HTTP 端点以注释形式保留
- 认证授权尚未完整闭环（当前主要覆盖 shell 权限审批）
- `ui/` 目前核心是事件渲染适配，不是完整多端 UI 子系统

## 演进方向（与现状兼容）

1. 先补齐认证与事件隔离（安全优先）
2. 将 runtime/service 从全局可变状态拆到连接级/用户级上下文
3. 统一 WS/HTTP 输出到 transport envelope
4. 再推进 UI/transport 插件化扩展

***

维护约定：

- 本文件只记录已落地实现
- 目标态设计请放独立计划文档，不与本文件混写
