# Pytest 使用技巧（速查）

**文档分级：A（只给项目成员｜内部）**

## 1) 运行方式与选择性执行

- 跑全部测试：
  - `uv run pytest`
  - `uv run pytest -q`（更安静）

- 只跑某个文件/某个测试：
  - `uv run pytest tests/test_async_tools.py`
  - `uv run pytest tests/test_async_tools.py::test_shell_stream_emits_tool_stream_events`

- 通过关键字筛选：
  - `uv run pytest -k shell_stream`（名字里包含 shell_stream 的测试）
  - `uv run pytest -k "shell_stream and not news"`（支持 and/or/not 组合）

- 更详细输出：
  - `uv run pytest -vv`
  - `uv run pytest -q -vv`（用例名更清楚 + 仍然比较安静）

## 2) 失败时的高效定位

- 遇到第一个失败就停：
  - `uv run pytest -x`

- 限制失败数量：
  - `uv run pytest --maxfail=1`

- 只重跑上次失败：
  - `uv run pytest --lf`

- 失败优先（先跑上次失败，再跑其余）：
  - `uv run pytest --ff`

- 看最慢的测试（性能定位）：
  - `uv run pytest --durations=10`

## 3) 输出与日志

- 捕获输出（pytest 默认会捕获 stdout/stderr；失败时再展示）：
  - 临时关闭捕获：`uv run pytest -s`

- 打印更多失败摘要：
  - `uv run pytest -ra`（显示 skipped/xfail 等摘要）
  - `uv run pytest -rA`（显示所有测试结果摘要）

## 4) fixture（为什么测试函数不需要“手动实例化/调用”）

pytest 会自动：
- 收集 `tests/` 目录下的 `test_*.py`
- 调用其中的 `test_*` 函数
- 如果 test 函数参数名匹配 fixture（如 `tmp_path`、`monkeypatch`），pytest 会自动创建并注入

常用 fixture：
- `tmp_path`：每个测试独立的临时目录（避免互相污染）
- `monkeypatch`：临时修改环境变量、模块属性、函数等（测试结束自动还原）

## 5) Mock / monkeypatch 技巧（你项目里常用）

- mock 网络：`httpx.MockTransport(handler)`
  - 在 `handler(request)` 里根据 URL 返回假 `httpx.Response(...)`
  - 这样测试不依赖真实网络、确定性更强

- monkeypatch 替换函数：
  - `monkeypatch.setattr(module, "name", fake_func)`
  - 常见用途：替换 LiteLLM 的 `litellm.completion` 让它返回可控的流式 chunks

## 6) 断言与调试

- pytest 的 `assert` 会自动做“断言重写”，失败时给出对比细节（比手写 raise 好用）。

- 进入调试器：
  - `uv run pytest --pdb`（失败自动进 pdb）
  - 或在代码里临时插入：`import pdb; pdb.set_trace()`

- 更严格地把警告当错误（排查不安全/弃用行为）：
  - `uv run pytest -W error`

## 7) 参数化（减少重复测试代码）

典型用法（示例）：

```python
import pytest

@pytest.mark.parametrize(
    "inp,expected",
    [("a", 1), ("bb", 2)],
)
def test_len(inp, expected):
    assert len(inp) == expected
```

## 8) 针对本项目的实用命令

- 只跑异步工具：
  - `uv run pytest -q -k async_tools -vv`

- 只跑 tool 调用循环相关：
  - `uv run pytest -q -k query_loop -vv`

- 只跑配置加载：
  - `uv run pytest -q -k config_load -vv`
