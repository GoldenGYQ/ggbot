# 安全与权限（Security）


本项目的安全边界目标：
- 工具只能在 workspace sandbox 内操作
- 高风险工具（shell、写文件、网络）要有明确的默认策略（确认/超时/截断/并发）
- transcript 不应泄露密钥与本机敏感路径

## 当前安全现状（2026-04 代码审计）

以下结论基于当前代码实际实现（`ggbot/api/*`, `ggbot/tools/*`, `ggbot/app/*`）：

### 高危

- 未鉴权工具执行：`POST /api/v1/tools/execute` 目前无认证/授权，且直接调用 `registry.call()`，在服务暴露时可能被远程触发高风险工具（如 shell）。
- CORS 过宽：API 允许 `allow_origins=["*"]`，在无身份边界时会放大浏览器侧调用风险。
- WS 全局事件泄漏：每个 WebSocket 连接都订阅全局事件总线，未按连接/会话隔离，可能看到其他会话的敏感事件数据（含权限请求参数）。

### 中危 / 架构风险

- 全局 runtime 并发污染：`send_message` 与 `switch_session` 共享并修改同一 `runtime` 状态，在多连接并发下存在串会话风险。
- 全局 APIService 单例耦合：单进程全局服务对象不适合多用户并发隔离，容易出现上下文串扰。

### 已有防护（仍需保留）

- Shell 默认确认：`shell_confirm=true`（可配置）。
- Shell 超时与输出截断：避免命令失控和上下文污染。
- 文件/工作区工具受 workspace root 约束。

## 优先级修复建议（建议按 P0/P1 执行）

- P0：为 HTTP 和 WS 增加 token 认证；默认拒绝未认证调用敏感接口。
- P0：收紧 CORS 白名单并校验 Origin；禁止 `*` 直开生产环境。
- P0：事件推送按 `connection_id/session_id` 过滤，避免跨会话广播。
- P1：将 runtime/service 改为按用户或连接隔离，避免全局可变状态竞争。
- P1：补充审计字段（`user_id/session_id/connection_id`）到关键权限事件。

## Workspace sandbox

- 沙箱根目录：`Settings.workspace_root`（环境变量 `GGBOT_WORKSPACE_ROOT`）
- 文件工具与 shell 工具在执行前必须检查路径是否在沙箱内

实现：`ggbot/core/permissions.py`。

## Shell 工具风险控制

### 默认策略

- `GGBOT_SHELL_CONFIRM=true`：每次执行前需要用户确认
- `GGBOT_SHELL_TIMEOUT_MS`：避免命令卡死
- `GGBOT_SHELL_MAX_OUTPUT_CHARS`：避免超长输出污染上下文与 transcript

### 建议

- 不要在 shell 输出中回显密钥（token、API key）
- 不要让模型“自动化执行删除/覆盖/格式化磁盘”等高风险命令
- 当需要批量操作时，优先写小脚本并进行人工 review，再通过 shell 执行

## 网络工具风险控制

仓库包含网络相关工具（例如 HTTP GET / 搜索）。原则：
- 默认设置超时
- 限制并发与输出长度
- 避免把本机路径/本地文件内容泄露到远端

## Transcript 与敏感信息

- transcript 会记录：用户输入、assistant 输出、工具调用与结果
- 风险：工具结果可能包含本地路径、环境变量信息、命令输出

建议：
- 默认不要把 `.env`、密钥文件内容读入/写入 transcript
- 分享 transcript 给他人前，必须先做脱敏

## 变更审查（建议的 checklist）

涉及以下内容的 PR 必须做安全 review：
- 新增/放宽文件读写范围
- 新增/修改 shell 工具能力（尤其是取消确认、提高超时/输出上限）
- 新增网络抓取与外部请求
- 修改 transcript 事件内容（可能引入敏感信息落盘）
