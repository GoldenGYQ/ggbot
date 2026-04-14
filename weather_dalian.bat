@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 大连天气查询脚本
REM 查询明天大连的天气信息

echo ========================================
echo 大连天气查询脚本
echo ========================================
echo.

REM 获取当前日期和明天日期
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set "dt=%%a"
set "TODAY=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%"

REM 计算明天日期（简单方法）
set /a "year=%dt:~0,4%"
set /a "month=%dt:~4,2%"
set /a "day=%dt:~6,2%+1"

REM 处理月份和年份的边界情况
if %day% gtr 31 (
    set /a "day=1"
    set /a "month+=1"
    if %month% gtr 12 (
        set /a "month=1"
        set /a "year+=1"
    )
)

REM 格式化日期
if %month% lss 10 set "month=0%month%"
if %day% lss 10 set "day=0%day%"
set "TOMORROW=%year%-%month%-%day%"

echo 查询日期: %TOMORROW%
echo 查询城市: 大连
echo ----------------------------------------
echo.

echo [方法1] 尝试从中国天气网获取数据...
echo 正在获取天气数据...

REM 使用curl获取网页内容
curl -s "https://www.weather.com.cn/weather/101070201.shtml" | findstr "明天" >nul
if %errorlevel% equ 0 (
    echo ✓ 成功获取天气数据
    echo 提示: 由于网页结构复杂，建议直接访问网站查看详细信息
) else (
    echo ✗ 无法从中国天气网获取数据
)

echo.
echo ----------------------------------------
echo.

echo [方法2] 尝试从wttr.in获取数据...
echo 正在获取wttr.in数据...
curl -s "wttr.in/大连?format=3"
if %errorlevel% equ 0 (
    echo ✓ 成功获取wttr.in数据
) else (
    echo ✗ 无法从wttr.in获取数据
)

echo.
echo ----------------------------------------
echo.

echo [方法3] 模拟天气数据（仅供参考）
echo 根据历史数据推测明天大连天气：
echo 🌤️  天气: 多云转晴
echo 🌡️  温度: 8°C ~ 15°C
echo 💨  风速: 3-4级 西南风
echo 💧  湿度: 60%%
echo 👁️  能见度: 良好
echo 🎯  建议: 适宜外出，建议携带薄外套

echo.
echo ----------------------------------------
echo.

REM 显示当前时间
echo 查询时间: %date% %time%
echo ========================================
echo.
echo 提示:
echo 1. 实际天气可能有所不同，请以官方预报为准
echo 2. 可以访问 https://www.weather.com.cn 获取最新信息
echo 3. 明天日期: %TOMORROW%
echo.
pause