# GGbot 增强日志功能

## 概述

GGbot 现在提供了增强的日志功能，包括：
1. **HTML日志导出** - 将日志导出为美观的HTML格式
2. **高级筛选功能** - 按角色、类型、内容等条件筛选日志
3. **大模型原始内容显示** - 查看大模型的原始输出内容
4. **统计信息** - 提供详细的日志统计信息

## 新命令

### 1. 增强日志查看器 (`log-enhanced`)

```bash
# 基本使用
uv 

# 导出为HTML
uv run ggbot log-enhanced --html --output session_log.html

# 只显示特定角色的消息
uv run ggbot log-enhanced --include-roles assistant,thinking

# 排除特定角色的消息
uv run ggbot log-enhanced --exclude-roles system

# 搜索特定内容
uv run ggbot log-enhanced --search "函数" --show-raw

# 显示统计信息
uv run ggbot log-enhanced --stats

# 组合筛选
uv run ggbot log-enhanced \
  --include-roles assistant,thinking \
  --min-length 50 \
  --max-length 500 \
  --search "代码"
```

### 2. 原始内容查看器 (`log-raw`)

```bash
# 查看大模型原始输出
uv run ggbot log-raw
```

## 筛选选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--include-roles` | 包含的角色 | `--include-roles assistant,thinking` |
| `--exclude-roles` | 排除的角色 | `--exclude-roles system` |
| `--include-types` | 包含的事件类型 | `--include-types model_message,tool_call` |
| `--exclude-types` | 排除的事件类型 | `--exclude-types status,turn_update` |
| `--search` | 搜索文本 | `--search "错误"` |
| `--min-length` | 最小内容长度 | `--min-length 100` |
| `--max-length` | 最大内容长度 | `--max-length 1000` |
| `--show-raw` | 显示原始内容 | `--show-raw` |
| `--stats` | 只显示统计信息 | `--stats` |
| `--html` | 导出为HTML | `--html --output log.html` |

## HTML日志功能

### 特性
1. **美观的界面** - 使用现代CSS样式
2. **颜色编码** - 不同角色使用不同颜色
3. **原始内容显示** - 显示大模型的原始输出
4. **工具调用展示** - 清晰显示工具调用信息
5. **时间戳** - 每个事件都有精确的时间戳
6. **统计面板** - 显示会话统计信息

### 示例HTML输出
生成的HTML文件包含：
- 会话概览和统计信息
- 按时间顺序排列的事件列表
- 每个事件的详细内容
- 大模型原始输出（如果可用）
- 工具调用参数

## 技术实现

### 新增模块
1. **`log_enhancer.py`** - 核心增强日志处理器
   - `LogFilter` - 日志筛选器类
   - `LogEvent` - 日志事件封装类
   - `LogEnhancer` - 日志增强器主类

2. **修改的文件**
   - `cli.py` - 添加新命令
   - `agent_loop.py` - 记录原始内容
   - `types.py` - 添加`raw_content`字段

### 数据流
```
大模型输出 → agent_loop记录原始内容 → 日志文件 → LogEnhancer处理 → HTML/控制台输出
```

## 使用场景

### 1. 调试和分析
```bash
# 查看大模型的实际输出
uv run ggbot log-raw

# 分析思考过程
uv run ggbot log-enhanced --include-roles thinking --show-raw
```

### 2. 质量检查
```bash
# 检查工具调用
uv run ggbot log-enhanced --include-types tool_call,tool_result

# 检查错误
uv run ggbot log-enhanced --search "错误" --include-types provider_error
```

### 3. 报告生成
```bash
# 生成HTML报告
uv run ggbot log-enhanced --html --output report.html

# 生成统计报告
uv run ggbot log-enhanced --stats > stats.txt
```

### 4. 性能分析
```bash
# 查看长时间运行的会话
uv run ggbot log-enhanced --min-length 500

# 分析交互模式
uv run ggbot log-enhanced --include-roles user,assistant
```

## 示例

### 示例1：生成完整的会话报告
```bash
# 生成包含所有详细信息的HTML报告
uv run ggbot log-enhanced \
  --html \
  --output full_session_report.html \
  --include-roles system,user,assistant,thinking,tool
```

### 示例2：分析代码相关交互
```bash
# 查找所有与代码相关的交互
uv run ggbot log-enhanced \
  --search "代码\|函数\|文件\|import\|def\|class" \
  --show-raw \
  --include-roles assistant,thinking
```

### 示例3：监控工具使用情况
```bash
# 查看所有工具调用
uv run ggbot log-enhanced \
  --include-types tool_call,tool_result \
  --stats
```

## 注意事项

1. **原始内容大小** - 大模型的原始输出可能很大，使用`--max-length`限制显示长度
2. **编码问题** - 中文内容在Windows控制台可能有编码问题，建议使用HTML导出
3. **性能考虑** - 处理大型日志文件时可能需要一些时间
4. **隐私安全** - HTML文件可能包含敏感信息，妥善保管

## 未来扩展

1. **实时监控** - 实时HTML日志查看
2. **图表分析** - 添加交互式图表
3. **导出格式** - 支持JSON、CSV等格式
4. **搜索增强** - 正则表达式搜索、模糊搜索
5. **对比功能** - 多个会话对比分析

## 故障排除

### 问题：编码错误
**症状**：控制台显示乱码或编码错误
**解决**：
```bash
# 使用HTML导出
uv run ggbot log-enhanced --html --output log.html

# 或设置环境变量
set PYTHONIOENCODING=utf-8
uv run ggbot log-enhanced
```

### 问题：无原始内容
**症状**：`log-raw`命令显示"No raw model content found"
**解决**：
- 确保使用最新代码
- 检查`agent_loop.py`中的`raw_content`字段是否正确设置
- 重新启动会话生成新的日志

### 问题：筛选无效
**症状**：筛选条件不生效
**解决**：
- 检查角色/类型名称是否正确
- 使用`--stats`查看可用的角色和类型
- 确保日志文件包含相关数据