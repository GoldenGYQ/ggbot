# 安全与权限（Security）

**文档分级：A（只给项目成员｜内部）**

本项目的安全边界目标：
- 工具只能在 workspace sandbox 内操作
- 高风险工具（shell、写文件、网络）要有明确的默认策略（确认/超时/截断/并发）
- transcript 不应泄露密钥与本机敏感路径

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
