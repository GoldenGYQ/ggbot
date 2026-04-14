#!/usr/bin/env python3
"""
最简单的天气查询脚本
使用wttr.in服务
"""

import sys
import subprocess
import platform

def get_weather(city):
    """使用curl获取天气"""
    try:
        # 检查系统类型
        system = platform.system()
        
        if system == "Windows":
            # Windows系统
            cmd = f'curl -s "wttr.in/{city}?format=3"'
            result = subprocess.run(['powershell', '-Command', cmd], 
                                  capture_output=True, text=True, encoding='utf-8')
        else:
            # Linux/Mac系统
            cmd = f'curl -s "wttr.in/{city}?format=3"'
            result = subprocess.run(cmd, shell=True, 
                                  capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return None
    except Exception as e:
        print(f"错误: {e}")
        return None

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python weather_simple.py <城市名>")
        print("示例: python weather_simple.py 北京")
        print("      python weather_simple.py \"New York\"")
        print("\n或者直接使用curl:")
        print("  curl wttr.in/北京")
        print("  curl wttr.in/北京?format=3  # 简洁格式")
        sys.exit(1)
    
    city = sys.argv[1]
    print(f"正在查询 {city} 的天气...")
    
    weather = get_weather(city)
    
    if weather:
        print(f"\n{weather}")
        print(f"\n更多信息:")
        print(f"  完整天气: curl wttr.in/{city}")
        print(f"  简洁格式: curl wttr.in/{city}?format=3")
        print(f"  当前天气: curl wttr.in/{city}?0")
        print(f"  3天预报: curl wttr.in/{city}?2")
    else:
        print(f"无法获取 {city} 的天气信息")
        print("请确保已安装curl: https://curl.se/download.html")

if __name__ == '__main__':
    main()