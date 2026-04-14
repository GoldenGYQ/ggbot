#!/bin/bash
# 简单天气查询脚本 - 使用curl和wget

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 检查参数
if [ $# -eq 0 ]; then
    echo "使用方法: $0 <城市>"
    echo "示例: $0 北京"
    echo "示例: $0 \"New York\""
    exit 1
fi

CITY="$*"
echo -e "${CYAN}正在查询 $CITY 的天气...${NC}"
echo ""

# 方法1: 使用wttr.in (简单可靠)
echo -e "${YELLOW}=== 方法1: wttr.in ===${NC}"
curl -s "wttr.in/$CITY?format=3"
echo ""
echo ""

# 方法2: 获取详细天气
echo -e "${YELLOW}=== 方法2: 详细天气信息 ===${NC}"
curl -s "wttr.in/$CITY?0"
echo ""

# 方法3: 获取ASCII艺术天气
echo -e "${YELLOW}=== 方法3: ASCII天气图 ===${NC}"
curl -s "wttr.in/$CITY"
echo ""

# 方法4: 获取天气预报
echo -e "${YELLOW}=== 方法4: 3天天气预报 ===${NC}"
curl -s "wttr.in/$CITY?2"
echo ""

echo -e "${GREEN}查询完成！${NC}"
echo "提示: 可以使用以下格式获取不同信息:"
echo "  curl wttr.in/$CITY          # 完整天气信息"
echo "  curl wttr.in/$CITY?format=3 # 简洁格式"
echo "  curl wttr.in/$CITY?0        # 当前天气"
echo "  curl wttr.in/$CITY?1        # 今天+明天"
echo "  curl wttr.in/$CITY?2        # 3天预报"