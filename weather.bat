@echo off
chcp 65001 >nul
echo 天气查询脚本
echo.

if "%1"=="" (
    echo 使用方法: weather.bat ^<城市名^>
    echo 示例: weather.bat 北京
    echo 示例: weather.bat "New York"
    exit /b 1
)

set CITY=%1
echo 正在查询 %CITY% 的天气...
echo.

rem 使用wttr.in服务
curl -s "wttr.in/%CITY%?format=3"
echo.
echo.

rem 显示更多信息
echo 更多天气信息:
echo   完整天气: curl wttr.in/%CITY%
echo   简洁格式: curl wttr.in/%CITY%?format=3
echo   当前天气: curl wttr.in/%CITY%?0
echo   3天预报: curl wttr.in/%CITY%?2