#!/usr/bin/env python3
"""
简单天气查询脚本
使用免费的天气API
"""

import requests
import json
import sys
from datetime import datetime

def get_weather(city):
    """获取天气信息"""
    try:
        # 使用免费的天气API
        url = f"https://wttr.in/{city}?format=j1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取天气信息失败: {e}")
        return None

def display_weather(data, city):
    """显示天气信息"""
    if not data:
        print(f"无法获取 {city} 的天气信息")
        return
    
    try:
        current = data['current_condition'][0]
        weather = data['weather'][0]
        
        print("=" * 50)
        print(f"城市: {city}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        # 温度和体感温度
        temp_c = current['temp_C']
        feelslike_c = current['FeelsLikeC']
        print(f"温度: {temp_c}°C")
        print(f"体感温度: {feelslike_c}°C")
        
        # 天气描述
        desc = current['weatherDesc'][0]['value']
        print(f"天气: {desc}")
        
        # 湿度和风速
        humidity = current['humidity']
        wind_speed = current['windspeedKmph']
        wind_dir = current['winddir16Point']
        print(f"湿度: {humidity}%")
        print(f"风速: {wind_speed} km/h {wind_dir}")
        
        # 能见度和气压
        visibility = current['visibility']
        pressure = current['pressure']
        print(f"能见度: {visibility} km")
        print(f"气压: {pressure} hPa")
        
        # 日出日落
        sunrise = weather['astronomy'][0]['sunrise']
        sunset = weather['astronomy'][0]['sunset']
        print(f"日出: {sunrise}")
        print(f"日落: {sunset}")
        
        print("=" * 50)
        
    except KeyError as e:
        print(f"数据格式错误: {e}")
    except Exception as e:
        print(f"显示天气信息时出错: {e}")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python weather.py <城市名>")
        print("示例: python weather.py 北京")
        print("示例: python weather.py \"New York\"")
        sys.exit(1)
    
    city = sys.argv[1]
    print(f"正在查询 {city} 的天气...")
    
    data = get_weather(city)
    display_weather(data, city)

if __name__ == "__main__":
    main()