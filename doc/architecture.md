# 架构（Architecture）

**文档分级：A（只给项目成员｜内部）**

## 文档目的

这份文档描述 **当前仓库真实架构**（不是目标态草图），用于：

- 新成员快速建立系统心智模型
- 评估改动影响范围（API / runtime / tools / transcript）
- 作为安全与重构讨论的统一参考

相关文档：

- 安全现状与风险：`doc/security.md`
- 认证与传输分层计划：`doc/user_auth_and_transport_split_plan.md`
- 当前问题清单：`doc/当前问题.md`

## 当前目录与职责（以代码为准）

```text
ggbot/
  command.py                     # CLI 入口（含 api 子命令）
  app/
    config.py                    # 配置加载（env/.env/toml）
    app_bootstrap.py             # runtime/bootstrap/session 初始化与切换
    client_factory.py            # LLM client 工厂
  api/
    server.py                    # FastAPI + WebSocket 路由与连接管理
    services.py                  # 会话、消息、工具执行、配置等业务服务
    permission_manager.py        # shell 权限请求/响应协调
  runtime/
    agent_loop.py                # run_query 主循环
    model_interaction.py         # 模型交互与输出处理
    tool_execution.py            # 工具执行与预算校验
    history_repair.py            # tool message 历史修复
  state/
    transcript.py                # transcript 读写与会话打开
    session_store.py             # sessions.json 元数据
    sessions.py                  # 默认会话发现
    session_meta.py              # 会话元信息模型
  events/
    event_bus.py                 # 全局事件总线
    runtime_events.py            # 事件消费/映射工具
    transcript_logger.py         # runtime event -> transcript 持久化
  tools/
    registry.py                  # 工具注册与调用
    manager.py                   # 内置工具装配
    context.py                   # ToolContext 注入
    file_tools.py / shell_*.py / http_tools.py / web.py / jobs_tool.py ...
  providers/
    litellm_client.py            # LLM provider 适配
    types.py                     # ChatCompletionClient 协议
  prompts/
    manager.py / builder.py / repository.py / types.py
  transport/
    transport_protocol.py        # runtime event envelope 编解码
    transcript_contract.py       # transcript 事件契约
  ui/
    renderers/tui_renderer.py    # TUI 事件渲染适配（当前仅此 UI 模块）
  workspace/
    permissions.py               # 工作区路径约束
    workspace_manager.py
```

## 启动与运行路径

### 1) CLI 模式

1. `python -m ggbot` -> `ggbot/__main__.py` -> `command.app()`
2. `command.py` 通过 `create_app_session()` + `create_agent_bootstrap()` 初始化 runtime
3. 调用 `run_query()` 执行一轮对话
4. 运行时事件写入 transcript，CLI 消费并输出

### 2) API 模式（当前前后端主要链路）

1. `ggbot api --host --port` 进入 `command.py:api`
2. 创建 `AgentRuntime` 后启动 `run_api_server()`
3. `api/server.py` 提供 HTTP + WS 接口
4. `api/services.py` 调用 `runtime.run_query`、`registry.call`、`session_store` 完成业务
5. 事件通过 WS 回推客户端，同时写入 transcript

## 核心对象关系

### AgentRuntime（`app/app_bootstrap.py`）

`AgentRuntime` 持有核心可变状态：

- `session_id`
- `transcript`
- `messages`
- `registry`
- `client`
- `system_message`

`switch_runtime_session()` 会替换 `session_id/transcript/messages`，这是当前会话切换基础。

### APIService（`api/services.py`）

服务层能力：

- 会话列表/创建/更新/删除/切换
- `send_message`（调用 `run_query`）
- `execute_tool`（直接调用 `registry.call`）
- 配置查询与更新
- 最近事件缓冲查询

## 事件与持久化模型

### Runtime Event

- 运行中事件通过 `events/event_bus.py` 发布
- `api/server.py` 在 WS 连接上订阅并转发
- `events/transcript_logger.py` 将事件映射并写入 transcript

### Transcript（事实源）

持久化位置：`state/transcript.py` 与 `state/session_store.py`。

常见事件类型：

- `model_message`
- `tool_call`
- `tool_result`
- `tool_stream`
- `status`
- `provider_error`
- `turn_update` / `turn_complete`

## 工具系统

- `tools/manager.py` 创建并注册内置工具
- `tools/registry.py` 提供 schema 导出与执行入口
- `ToolContext` 注入用于事件发射与会话上下文
- 工具预算由 `runtime/agent_loop.py` 中 `ToolLimits` 与执行逻辑控制

## 传输协议层

`transport/transport_protocol.py` 提供稳定 envelope：

- `version`
- `session_id`
- `seq`
- `ts_ms`
- `source`
- `event_type`
- `data`

当前 API 实现尚未完全统一到该 envelope；`api/server.py` 仍在使用自定义 WS 消息结构。

## 当前架构约束（必须知晓）

以下是当前实现事实，不是目标态：

- API 模式使用全局 `runtime/APIService`，属于单上下文共享状态模型
- WS 连接默认订阅全局事件总线，隔离粒度仍需增强
- HTTP 接口已具备工具执行能力，但认证授权尚未完善
- `ui/` 目前只有 `tui_renderer.py`，更接近事件渲染层而非完整 UI 子系统

## 演进方向（和现状兼容）

1. 先补齐认证与事件隔离（安全优先）
2. 再把 runtime/service 从全局可变状态拆到用户/连接级上下文
3. 统一 WS/HTTP 事件输出到 transport envelope
4. 最后再扩展 UI/transport 插件化

---

维护约定：

- 本文件只记录已落地实现。
- 设计草案放在独立计划文档，不在本文件混写目标态。
