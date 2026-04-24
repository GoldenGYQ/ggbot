# GGbot 文档索引（内部）

**文档分级：A（只给项目成员｜内部）**

## 你应该先看什么

- 如果你是第一次接触项目：先看 [../README.md](../README.md)
- 如果你要接 API 做业务：看 [API_README.md](API_README.md)
- 如果你要理解代码结构和主链路：看 [architecture.md](architecture.md)
- 如果你要开始改代码：看 [development.md](development.md)

## 按目标阅读

- 本地部署与配置：
  - [../README.md](../README.md)
  - [configuration.md](configuration.md)
- API 集成（REST / WebSocket / 事件）：
  - [API_README.md](API_README.md)
- 架构理解（层级、主链路、设计取舍）：
  - [architecture.md](architecture.md)
- 当前风险与待办：
  - [当前问题.md](当前问题.md)
- 开发协作：
  - [development.md](development.md)
  - [contributing.md](contributing.md)

## 文档维护原则

- 只写“当前代码已实现”的事实，不写目标态幻想。
- 路径、函数名、类名优先与代码一致（如 `AgentRuntime`、`run_query()`、`Transcript`）。
- 架构图和流程图优先中文描述，关键符号保留英文名便于跳代码。
- 行为变化必须同步更新至少三处：
  - `README.md`
  - 对应 `doc/*.md`
  - `tests/`（有行为变化必须有测试）
