#!/bin/bash

# 简单的大连天气查询脚本
# 使用wttr.in服务获取天气信息

echo "=== 大连天气查询 ==="
echo "查询时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "查询城市: 大连"
echo ""

# 使用wttr.in服务
echo "正在获取天气信息..."
echo ""
curl -s "wttr.in/大连?format=v2"
echo ""

# 显示明天的天气预报
echo "=== 明天天气预报 ==="
curl -s "wttr.in/大连?1" | head -7
echo ""

# 显示建议
echo "=== 出行建议 ==="
echo "1. 根据天气预报准备合适的衣物"
echo "2. 关注天气变化，及时调整行程"
echo "3. 更多详细信息请访问: https://wttr.in/大连"
echo ""