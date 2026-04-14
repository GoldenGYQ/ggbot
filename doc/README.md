# GGbot 文档索引（内部）

**文档分级：A（只给项目成员｜内部）**

这套文档面向两类读者：
- 使用者：想把 GGbot 跑起来、能复盘一轮对话
- 维护者：要新增/修改工具、改 query loop、改 provider、保证 transcript 兼容

## 入口

- 项目入口（先读这个）：[README.md](../README.md)
- 架构与数据流：[architecture.md](architecture.md)
- 通用 Agent 迁移映射：[agent_migration_map.md](agent_migration_map.md)
- 开发指南：[development.md](development.md)
- 配置与运行（LiteLLM / 环境变量 / transcript）：[configuration.md](configuration.md)
- 安全与权限边界（workspace sandbox、shell/network 风险）：[security.md](security.md)
- 测试策略与速查：[tests.md](tests.md)
- 常见故障排查：[troubleshooting.md](troubleshooting.md)
- 贡献流程：[contributing.md](contributing.md)

## 文档分级约定

- A：只给项目成员（内部）
- B：可给公司内部相关团队（默认不含密钥/敏感路径）
- C：可公开（对外 README/示例，不包含内部细节）

当前仓库内 `doc/` 目录默认按 A 编写（除非文件头显式标注为 B/C）。
