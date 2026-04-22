# 贡献指南（Contributing）


## 原则

- 小步提交：每个 PR 聚焦一个主题
- 行为变更必须有测试
- 关键约定不破坏：tool message 顺序、transcript 兼容、workspace sandbox
- 文档随代码更新（README + doc/）

## 开发流程（建议）

1) 新建分支
2) 本地跑：`uv run pytest`
3) 提交 PR
4) Review checklist 通过后合并

## Review checklist

- [ ] 新增/修改功能是否有对应测试（`tests/`）
- [ ] 是否更新 README/doc（尤其配置/命令/行为变化）
- [ ] 是否影响 transcript 兼容性（旧 JSONL 能否继续读取/恢复）
- [ ] 是否引入新的高风险工具能力（shell/network/file write）
- [ ] 是否遵守 workspace sandbox（不允许越界读写）
- [ ] 是否有明显的循环风险（工具重复调用；budget 配置是否合理）

## 版本与发布（当前阶段）

当前属于 MVP 阶段，建议至少维护：
- `pyproject.toml` 的版本号
- CHANGELOG（如果后续需要）

当准备对外发布时再补：
- build 与发布流程
- 更严格的安全与脱敏规范
