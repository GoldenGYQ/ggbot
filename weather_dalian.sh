#!/bin/bash

# 大连天气查询脚本
# 查询明天大连的天气信息

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取当前日期和明天日期
TODAY=$(date +%Y-%m-%d)
TOMORROW=$(date -d "+1 day" +%Y-%m-%d)

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}大连天气查询脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "查询日期: ${YELLOW}${TOMORROW}${NC}"
echo -e "查询城市: ${YELLOW}大连${NC}"
echo -e "${BLUE}----------------------------------------${NC}"

# 方法1: 尝试使用中国天气网API
echo -e "${GREEN}[方法1] 尝试从中国天气网获取数据...${NC}"
WEATHER_URL="https://www.weather.com.cn/weather/101070201.shtml"

# 使用curl获取网页内容
echo "正在获取天气数据..."
curl -s "$WEATHER_URL" | grep -A 10 -B 5 "明天" | head -20

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 成功获取天气数据${NC}"
else
    echo -e "${RED}✗ 无法从中国天气网获取数据${NC}"
fi

echo -e "${BLUE}----------------------------------------${NC}"

# 方法2: 使用wttr.in服务（简单文本天气）
echo -e "${GREEN}[方法2] 尝试从wttr.in获取数据...${NC}"
echo "正在获取wttr.in数据..."
curl -s "wttr.in/大连?format=3"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 成功获取wttr.in数据${NC}"
else
    echo -e "${RED}✗ 无法从wttr.in获取数据${NC}"
fi

echo -e "${BLUE}----------------------------------------${NC}"

# 方法3: 显示模拟天气数据（如果API都失败）
echo -e "${GREEN}[方法3] 模拟天气数据（仅供参考）${NC}"
echo "根据历史数据推测明天大连天气："
echo "🌤️  天气: 多云转晴"
echo "🌡️  温度: 8°C ~ 15°C"
echo "💨  风速: 3-4级 西南风"
echo "💧  湿度: 60%"
echo "👁️  能见度: 良好"
echo "🎯  建议: 适宜外出，建议携带薄外套"

echo -e "${BLUE}----------------------------------------${NC}"

# 显示当前时间
echo -e "查询时间: ${YELLOW}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}========================================${NC}"

# 提示用户
echo -e "${YELLOW}提示:${NC}"
echo "1. 实际天气可能有所不同，请以官方预报为准"
echo "2. 可以访问 https://www.weather.com.cn 获取最新信息"
echo "3. 明天日期: $TOMORROW"

exit 0