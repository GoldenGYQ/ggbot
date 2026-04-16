# GGbot 实时流式输出与前端 UI 修复文档

## 1. 问题背景
在之前的版本中，虽然 API 接口支持 `stream=true` 参数，但前端感知到的输出存在严重延迟：
- **表现**：用户发送消息后，前端长时间处于等待状态，直到后端 Agent 循环全部结束（包括多轮对话和工具执行）后，所有事件才瞬间“爆发式”流式输出。
- **后果**：用户无法实时看到 AI 的思考过程和中间工具执行进度，严重影响交互体验。

## 2. 核心原因分析
经过排查，瓶颈主要存在于后端 API 服务的架构设计：
1. **同步阻塞模式**：`APIService.send_message` 在调用 `run_query` 时，虽然在线程中运行，但它会等待整个 Agent 循环结束后才返回收集到的所有 `events`。
2. **非实时分发**：FastAPI 的流式接口 `_stream_send_message` 实际上是在拿到后端返回的完整 `events` 列表后，才开始遍历并 `yield`。这意味着它只是在“模拟”流式，而不是真正的实时流。

## 3. 修复方案：异步队列与实时回调
我们通过重构 Agent 内核到 API 层的通信链路，实现了真正的实时流式推送。

### 3.1 内核层支持 (Runtime Kernel)
- **[agent_loop.py](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/runtime/agent_loop.py)**: 为 `run_query` 增加了 `event_callback` 参数。每当内核产生一个 `RuntimeEvent`（如 `turn_update`, `tool_call`, `turn_complete`），都会立即触发该回调。
- **[model_interaction.py](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/runtime/model_interaction.py)**: 在模型生成文本的 `on_delta` 回调中，增加了对 `event_callback` 的调用。这确保了每一个 Token (delta) 都能在产生的瞬间被推送到上层。

### 3.2 API 服务层打通 (Service Layer)
- **[services.py](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/api/services.py)**: `send_message` 方法现在支持接收并向下传递 `event_callback`。它不再仅仅依赖于最后的 `EventsCollector` 返回结果，而是允许上层实时截获事件。

### 3.3 FastAPI 异步流式转发 (Server Layer)
- **[server.py](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/api/server.py)**: 
    - 使用 `asyncio.Queue` 建立了异步事件缓冲区。
    - 引入 `loop.call_soon_threadsafe`，确保从工作线程产生的事件能安全地放入主事件循环的队列中。
    - `_stream_send_message` 现在采用生产者-消费者模式：后台任务生产事件放入队列，流式生成器持续消费队列并 `yield` 给客户端。

## 4. 前端 UI 增强 (Vue Frontend)
在 [example/vue_frontend](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/example/vue_frontend) 中，我们实现了一套类似“豆包”风格的界面：

### 4.1 核心组件
- **[ThinkingBox.vue](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/example/vue_frontend/ggbot-vue/src/components/ThinkingBox.vue)**: 专门处理 `thinking` 事件，支持思考过程的展开与折叠。
- **[MessageItem.vue](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/example/vue_frontend/ggbot-vue/src/components/MessageItem.vue)**:
    - **实时渲染**：基于 `assistant_delta` 实现逐字显示的打字机效果。
    - **工具状态**：根据 `tool_call` 和 `tool_result` 实时更新工具执行状态（执行中/已完成/失败）。
    - **代码高亮**：集成了 `markdown-it` 和 `highlight.js`。

### 4.2 交互逻辑
- **会话历史**：修复了 Store 中的 `fetchSessions` 逻辑，确保切换会话时能正确从后端加载历史消息。
- **流式解析**：前端 `api.sendMessage` 接收 `ReadableStream`，通过逐行解析 NDJSON 格式的事件流，实现真正的异步更新。

## 5. 验证方法
- **单元测试**：使用 `uv run pytest tests/test_api_basic.py` 等命令验证 API 稳定性。
- **专项测试**：运行 `uv run python ggbot/api/test_stream.py`。
    - **预期结果**：控制台应能实时看到 `assistant_delta` 逐字跳出，而不是成块出现。
- **界面测试**：在前端输入复杂指令（如搜索并提炼结论），观察“思考中”、“正在执行工具”等气泡是否随着后端进度实时切换。

## 6. 架构经验总结：内存级 Pub/Sub vs. 异步队列 (Async Queue)

在修复过程中，我们对比了 TUI (Terminal UI) 和 Web API 的不同实现模式，总结出以下设计经验：

### 6.1 TUI 模式：内存级发布订阅 (Pub/Sub)
TUI 渲染器通过订阅全局 `EventBus` 实现实时更新。
- **优点**：解耦彻底，只要有事件发布，UI 就能响应，适合单用户、进程内的直接交互。
- **局限性**：由于 `EventBus` 是全局广播的，在多用户并发的 API 环境下，需要复杂的 `session_id` 过滤逻辑，否则会产生消息串扰。同时，在工作线程直接操作异步 UI 存在安全隐患。

### 6.2 API 模式：异步队列 (Async Queue)
本次修复为 Web API 采用了专用的异步队列模式。
- **设计选择**：每个 HTTP 请求在 [server.py](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/api/server.py) 中拥有独立的 `asyncio.Queue`。
- **优势**：
    - **天然隔离**：不同请求的队列互不干扰，无需额外过滤逻辑，完美支持高并发。
    - **流量控制 (Backpressure)**：队列可以作为缓冲区，平衡后端 Token 爆发产生速度与网络传输速度之间的差异，使渲染更平滑。
    - **异步友好**：利用 `loop.call_soon_threadsafe` 将跨线程回调安全地转为异步流，符合 FastAPI 的异步编程范式。

### 6.3 适用场景建议
- **Pub/Sub**：适用于“一对多”的广播场景，如系统日志监控、全局状态同步或调试工具。
- **Async Queue**：适用于“一对一”的精准交付场景，如 Web 消息流、异步任务处理或需要严格数据隔离的业务逻辑。
###6.4这是一个非常专业的设计权衡问题。在不进行大规模重构的前提下，我们来对比一下这两种模式的适用性：

### 6.4 设计权衡
**1. 内存级发布订阅 (Pub/Sub) 能用到 API 上吗？**
**答案是：可以，但会有“干扰”问题。**

*   **原理**：API 服务可以像 TUI 一样订阅全局 `EventBus`。
*   **挑战**：`EventBus` 是全局共享的。如果 API 服务器同时处理 10 个用户的请求，全局总线会广播所有 10 个人的事件。API 需要一套复杂的**过滤机制**（例如通过 `session_id` 过滤）来确保用户 A 不会收到用户 B 的消息。
*   **重构代价**：虽然不需要重构 Agent 内核，但你需要修改 API 层的订阅逻辑，增加过滤层，并处理订阅对象的生命周期管理（请求结束时必须取消订阅，否则会导致内存泄漏）。

 **2. 异步队列 (Async Queue) 能用到 TUI 上吗？**
**答案是：非常适合，甚至可能是更好的选择。**

*   **原理**：目前 TUI 使用 `call_soon_threadsafe` 直接操作 UI 渲染（见 [tui_renderer.py:L43](file:///d:/Users/gyq16/Desktop/PRJ/GGbot/ggbot/ggbot/ui/renderers/tui_renderer.py#L43)），这实际上是一种“推”模式。如果换成队列，就变成了“拉”模式。
*   **优势**：使用队列可以起到**缓冲和削峰填谷**的作用。当模型输出极快（Token 爆发）时，UI 渲染如果跟不上，直接操作 UI 可能会导致界面卡顿。如果放入队列，UI 线程可以按照自己的节奏（例如每 16ms 刷新一次）从队列中取数据渲染，体验会更平滑。
*   **重构代价**：很小。只需要把 TUI 的回调函数改为 `queue.put`，然后在 TUI 的主循环里增加一个监听队列的任务即可。

---

 **总结对比：哪个更好？**

| 维度 | 内存级 Pub/Sub (TUI 模式) | 异步队列 (我刚写的 API 模式) |
| :--- | :--- | :--- |
| **隔离性** | **差**。全局广播，需要手动过滤多用户数据。 | **强**。每个请求拥有独立的队列，天然隔离。 |
| **异步安全性** | **中**。回调函数在工作线程运行，操作异步 UI 需谨慎。 | **高**。队列是线程安全的，完美契合 `async/await`。 |
| **流量控制** | **无**。产生多少推多少，可能压垮慢速客户端。 | **有**。可以通过队列长度控制节奏，支持背压。 |
| **重构代价** | 适合单机单用户工具 (CLI/TUI)。 | **最适合 Web API 服务**。 |

**我的建议：**

在**不大量重构**的前提下：
- **API 维持现在的异步队列模式**是最佳选择。因为它能完美解决**多并发请求的隔离**问题，且不需要动全局的 `EventBus` 逻辑。
- **TUI 维持现在的 Pub/Sub 模式**也是合理的，因为 TUI 通常是单用户、单会话运行，全局总线带来的干扰极小，且实现起来最直接。

**一句话总结**：
Pub/Sub 适合“**一对多**”的广播场景（如日志监控、调试）；异步队列适合“**一对一**”的精准交付场景（如 Web 请求、任务处理）。我刚写的修复方案正是为了给每个 Web 请求提供一个专属的“私人管道”。）。”。私人“传送带”）。
## 7. 总结
此次修复将 GGbot 从“请求-完整响应”模式彻底转变为“实时事件驱动”模式。这不仅提升了视觉上的流畅度，更重要的是为用户提供了 Agent 执行过程中的透明度，使用户能够在中途发现偏差并及时干预。
