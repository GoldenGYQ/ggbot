# 模型流式 JSON 与工具调用读取说明

## 1. 结论先看

- `stream=true` 时，模型返回的是**连续的结构化 chunk JSON**，不是纯文本流。
- 文本增量来自 `choices[0].delta.content`。
- 工具调用增量来自 `choices[0].delta.tool_calls`。
- 最终执行工具时，使用的是“按 `index` 合并后的完整 `tool_calls`”，不是每个 chunk 来一次就执行一次。
- 当前工程已支持把 provider 原始 chunk 透传为 `provider_chunk` 事件（可 WS 实时看、也会写 transcript）。

## 2. 为什么官方示例常写 `choices[0].message`

- 非流式（`stream=false`）：一次返回完整对象，通常读取 `choices[0].message`。
- 流式（`stream=true`）：多次返回 chunk，每次读 `choices[0].delta`，最终由客户端自行拼接成完整消息。

两者并不冲突，只是调用模式不同。

## 3. 典型流式 chunk 结构

下面是常见 OpenAI-compatible chunk 形态（示意）：

```json
{
  "id": "xxx",
  "created": 177702220,
  "model": "deepseek-chat",
  "object": "chat.completion.chunk",
  "choices": [
    {
      "index": 0,
      "delta": {
        "content": null,
        "tool_calls": null
      },
      "finish_reason": "stop"
    }
  ]
}
```

说明：
- `delta.content`：文本增量片段。
- `delta.tool_calls`：工具调用增量片段（可能拆成多段）。
- `finish_reason`：结束信号（如 `stop` / `tool_calls` / `length`）。
- 其他字段（`logprobs`/`audio`/`provider_specific_fields` 等）常为兼容预留，可能长期为 `null`。

## 4. 本项目如何读取这些字段

读取入口在 `ggbot/providers/litellm_client.py`：

1. 每个 chunk 转成字典：
   - `obj = _to_dict(chunk)`
2. 读取首个 choice：
   - `choices = obj.get("choices") or []`
   - `c0 = choices[0] or {}`
   - `delta = c0.get("delta") or {}`
3. 读取文本增量：
   - `text = delta.get("content")`
   - 若存在则 `on_text_delta(text)` 并追加到 `content_parts`
4. 读取工具调用增量：
   - `tc_list = delta.get("tool_calls") or []`
   - 对每个 `tc` 提取 `index/id/function.name/function.arguments`
   - 调用 `_merge_tool_call_delta(...)` 合并到 `tool_calls[index]`
5. 收到 `finish_reason` 后结束流式循环并返回：
   - `AssistantFinal(content="".join(content_parts), tool_calls=[...])`

## 5. 工具调用会不会重复执行

正常不会，原因：
- 流式阶段只做“增量合并”，不执行工具。
- 执行发生在模型回合结束后，`run_query` 对最终 `turn_outcome.tool_calls` 执行一次。
- 所以单次模型回合中，工具执行基于合并后的最终列表，不是基于每个 chunk。

## 6. `content` 与 `tool_calls` 会不会同时出现

会。协议允许同一轮里既有文本也有工具调用（或者仅其一）。

当前实现会分别处理：
- 文本走 `delta.content`
- 工具调用走 `delta.tool_calls`

最终 `assistant` 消息会同时携带：
- `content`
- `tool_calls`（若非空）

## 7. `tool_call.id` 来源说明

- 优先使用 provider/模型返回的 `delta.tool_calls[*].id`。
- 若某个索引暂未拿到 id，本地会用 `tool_{index}` 作为临时占位。
- 一旦后续 chunk 带了真实 id，会覆盖占位值。

因此：
- `call_xxx` 常见于 provider 原生 id；
- `tool_0/tool_1` 更像本地兜底占位；
- 仅看最终 transcript，通常无法 100% 判断 id 来源，除非记录原始 chunk（本项目已支持）。

## 8. 原始 chunk 的实时观测

当前工程新增了 `provider_chunk` 事件链路：

- Provider 层：捕获每个原始 chunk（`on_raw_chunk`）。
- Runtime 层：写入 transcript（`provider_chunk`）并发出 runtime event。
- API/WS 层：通过 WS 实时推送。
- 页面层：`后台会话查看.html` 右侧面板可实时查看原始 chunk JSON。

这条链路的价值是：
- 还原 provider 原始输出；
- 排查“字段来源”与“合并逻辑”是否正确；
- 验证工具调用 id 与参数增量拼接过程。

## 9. 常见误区

- 误区：流式就是纯文本。
  - 实际：流式是结构化 JSON chunk 的连续序列，文本只是其中一个字段。
- 误区：`tool_calls` 出现时 `content` 一定为空。
  - 实际：可能为空，也可能同时有文本，取决于模型与策略。
- 误区：每个 `tool_calls` chunk 都会触发工具执行。
  - 实际：不会，先合并，回合结束后再执行。
