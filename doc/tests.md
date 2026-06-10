# GGbot 测试指南

## 快速运行

```bash
# 运行所有测试
pytest

# 仅运行单元测试（无需 API key / 外部服务）
pytest -m unit

# 仅运行集成测试（需要真实 API key 或运行中的服务器）
pytest -m integration

# 排除需要 API key 的测试
pytest -m "not need_api_key"

# 运行特定文件
pytest tests/test_thinking.py -v

# 按关键词筛选
pytest -k "tool_registry" -v

# 显示最慢的 10 个测试
pytest --durations=10

# 失败时进入调试器
pytest --pdb
```

## 测试文件组织

| 文件 | 类型 | Marker | 说明 |
|---|---|---|---|
| `test_api.py` | 手动脚本 | — | 端到端冒烟测试，需手动启动服务器 |
| `test_api_basic.py` | 单元 | `@pytest.mark.unit` | API 模块导入与服务器创建 |
| `test_api_integration.py` | 集成 | `@pytest.mark.need_api_key` | WebSocket/REST 全链路测试 |
| `test_api_permission_manager.py` | 单元 | `@pytest.mark.unit` | 权限管理器 request/resolve/timeout |
| `test_async_tools.py` | 单元 | `@pytest.mark.unit` | shell_stream 实时输出事件 |
| `test_background_jobs.py` | 单元 | `@pytest.mark.unit` | shell_run 后台任务与 job 日志 |
| `test_cli_init.py` | 单元 | `@pytest.mark.unit` | `ggbot init` 命令 |
| `test_cli_log.py` | 单元 | `@pytest.mark.unit` | `ggbot log` 命令渲染 |
| `test_config_integration.py` | 单元 | `@pytest.mark.unit` | 环境变量 / TOML / .env 优先级 |
| `test_config_load.py` | 单元 | `@pytest.mark.unit` | Settings.load 加载流程 |
| `test_docx_tools.py` | 单元 | `@pytest.mark.unit` | DOCX 创建/编辑/表格/样式 |
| `test_domain_transport_cleanup.py` | 单元 | `@pytest.mark.unit` | runtime_models 不包含 transport 模型 |
| `test_litellm_streaming.py` | 单元 | `@pytest.mark.unit` | LiteLLM 流式 delta 合并 |
| `test_permissions.py` | 单元 | `@pytest.mark.unit` | 工作区路径权限 enforce |
| `test_pets_render.py` | 单元 | `@pytest.mark.unit` | 示例宠物精灵渲染 |
| `test_prompt_manager.py` | 单元 | `@pytest.mark.unit` | Prompt 构建与自定义 profile |
| `test_provider_error_handling.py` | 单元 | `@pytest.mark.unit` | ProviderError 转 system message |
| `test_query_loop_tool_calls.py` | 单元 | `@pytest.mark.unit` | agent loop 工具执行/预算/历史修复 |
| `test_runtime_events.py` | 单元 | `@pytest.mark.unit` | RuntimeEvent 类型验证 |
| `test_session_meta.py` | 单元 | `@pytest.mark.unit` | 会话元数据持久化 |
| `test_session_store.py` | 单元 | `@pytest.mark.unit` | SessionStore 加载/列表/标题 |
| `test_shell_confirm_callback.py` | 单元 | `@pytest.mark.unit` | Shell 确认回调与路径验证 |
| `test_skills.py` | 单元 | `@pytest.mark.unit` | SkillResolver 触发与优先级 |
| `test_status_tool.py` | 单元 | `@pytest.mark.unit` | status_update 事件写入 |
| `test_thinking.py` | 单元 | `@pytest.mark.unit` | Thinking 内容提取（中/英/XML） |
| `test_tool_printer.py` | 单元 | `@pytest.mark.unit` | tool_printer 回调调用 |
| `test_tool_registry.py` | 单元 | `@pytest.mark.unit` | 工具注册/校验/schema/上下文注入 |
| `test_transcript_resume.py` | 单元 | `@pytest.mark.unit` | Transcript 读写/验证/清除 |
| `test_web_tools.py` | 单元 | `@pytest.mark.unit` | web_search / web_fetch（mock） |
| `test_web_tools_basic.py` | 单元 | `@pytest.mark.unit` | web 工具基本操作（mock） |
| `test_workspace_restriction.py` | 单元 | `@pytest.mark.unit` | 工作区路径限制 enforce |
| `test_workspace_tools.py` | 单元 | `@pytest.mark.unit` | workspace_create / workspace_list |

## Marker 说明

| Marker | 用途 | 示例 |
|---|---|---|
| `unit` | 纯单元测试，无外部依赖 | `pytest -m unit` |
| `integration` | 需要运行中的服务器 | `pytest -m integration` |
| `need_api_key` | 需要真实 LLM API key | `pytest -m "not need_api_key"` |
| `slow` | 运行较慢的测试 | `pytest -m "not slow"` |

## 添加新测试的约定

1. **文件名**：`test_<module_name>.py`
2. **模块 docstring**：每个文件顶部用 `"""一句话说明测试范围"""`
3. **函数 docstring**：每个测试函数用 `"""测什么 · 前提条件 · 预期结果"""`
4. **Marker**：纯单元测试加 `@pytest.mark.unit`，需要外部服务加对应 marker
5. **风格**：使用 `from __future__ import annotations`、类型注解、`tmp_path` fixture
6. **旧式脚本**：新测试请用 pytest，不要用 `test_api.py` 中的 print 式脚本风格
