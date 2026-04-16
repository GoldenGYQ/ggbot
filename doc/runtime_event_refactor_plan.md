# Runtime Event 收敛重构计划

## 背景
当前代码中存在多份事件模型与映射逻辑并存：
- `core/domain.py` 中定义 `RuntimeEvent`（领域事件）
- `core/runtime_events.py` 中再次定义 `RuntimeEvent`（兼容包装）
- `core/transcript_logger.py` 与 `core/runtime_events.py` 各自维护映射表
- `core/transport_protocol.py` 与 `core/domain.py` 各自维护传输事件结构

这导致同名异义、映射漂移、调用边界不清晰，属于高风险架构债务。

## 总目标
1. 单一事实来源（SSOT）：事件类型映射集中管理。
2. 明确边界：领域事件、兼容包装、传输封装分层清晰。
3. 兼容优先：不破坏现有 CLI/TUI/API 行为与测试。

## 分阶段方案

### 阶段 1（已完成）
目标：先止血，消除“重复映射+错误契约”

改造点：
1. 新增集中映射模块（例如 `core/event_mappings.py`）
   - transcript -> domain
   - domain -> transcript
2. `core/runtime_events.py`
   - 复用集中映射，不再内嵌硬编码 map
   - 修复 `consume_runtime_events` 的缺失分支
3. `core/transcript_logger.py`
   - 复用集中映射
   - `log_runtime_event` 不再依赖 `event.to_transcript_event()`（避免错误契约）

验收标准：
- 相关测试通过：`test_event_system.py`、`test_tui_event_handler.py`、`test_new_architecture.py`
- 全量测试通过：`uv run pytest -q`
- 关键模块无新增静态错误

### 阶段 2（已完成）
目标：减少双 RuntimeEvent 模型造成的认知负担

改造点：
1. 统一核心内部流转使用 `domain.RuntimeEvent`
2. `runtime_events.py` 降级为兼容适配层（仅保留必要入口）
3. 收敛 import，避免 `RuntimeEvent` 来源混用
4. 移除兼容窗口：`runtime_event(...)` 仅接受 `domain.RuntimeEventType`

验收标准：
- 移除主路径对兼容 RuntimeEvent 的依赖
- 兼容层已删除，不再接受 transcript 事件类型输入

### 阶段 3（已完成）
目标：传输层模型收敛

改造点：
1. 收敛 `TransportEvent` 与 `TransportEnvelope` 二选一（已选择 `TransportEnvelope`）
2. 明确版本化协议与领域事件边界
3. 清理重复序列化逻辑

验收标准：
- transport 相关测试通过
- 编码/解码路径单一

当前进展：
- 已删除 `core/domain.py` 中未被使用的 `TransportEvent`
- 传输层唯一结构为 `core/transport_protocol.py::TransportEnvelope`
- `runtime_event` 保持 domain-only 事件输入，传输类型转换仅通过 `runtime_event_to_transcript_type`

## 完成状态
- 事件模型单一来源：`domain.RuntimeEvent`
- 传输模型单一结构：`transport_protocol.TransportEnvelope`
- 测试与文档已同步，迁移任务无遗留兼容尾巴

## 风险与回滚策略
- 风险：事件类型映射变更导致部分回调不触发。
- 缓解：先补测试，再改映射；每阶段都跑全量测试。
- 回滚：阶段性提交，按 commit 粒度回滚。

## 实施顺序
1. 落地阶段 1（本次开始）
2. 通过回归后提交独立 commit
3. 再推进阶段 2
