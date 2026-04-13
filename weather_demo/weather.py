#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import sys
import json

def get_weather(city):
    """
    获取指定城市的天气信息
    
    Args:
        city (str): 城市名称，如 "Beijing", "Shanghai"
    
    Returns:
        dict: 天气信息字典，包含城市名、温度、天气状况等
    """
    # wttr.in 免费天气API，无需API key
    # 使用 format=j1 获取JSON格式数据
    url = f"https://wttr.in/{city}?format=j1"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 检查HTTP错误
        
        # 解析JSON数据
        weather_data = response.json()
        
        # 提取所需信息
        current_condition = weather_data.get("current_condition", [{}])[0]
        nearest_area = weather_data.get("nearest_area", [{}])[0]
        
        # 获取城市名
        city_name = nearest_area.get("areaName", [{}])[0].get("value", city)
        
        # 获取温度和天气状况
        temp_c = current_condition.get("temp_C", "N/A")
        temp_f = current_condition.get("temp_F", "N/A")
        feels_like_c = current_condition.get("FeelsLikeC", "N/A")
        
        # 获取天气描述
        weather_desc = "N/A"
        weather_desc_list = current_condition.get("weatherDesc", [{}])
        if weather_desc_list and isinstance(weather_desc_list, list):
            weather_desc = weather_desc_list[0].get("value", "N/A")
        
        # 获取其他信息
        humidity = current_condition.get("humidity", "N/A")
        wind_speed = current_condition.get("windspeedKmph", "N/A")
        wind_dir = current_condition.get("winddir16Point", "N/A")
        
        return {
            "city": city_name,
            "temperature_c": temp_c,
            "temperature_f": temp_f,
            "feels_like_c": feels_like_c,
            "weather_description": weather_desc,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "wind_direction": wind_dir,
            "raw_data": weather_data  # 保留原始数据供调试
        }
        
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None

def print_weather_info(weather_info):
    """
    格式化打印天气信息
    
    Args:
        weather_info (dict): 天气信息字典
    """
    if not weather_info:
        print("无法获取天气信息")
        return
    
    print("=" * 50)
    print(f"城市: {weather_info['city']}")
    print(f"温度: {weather_info['temperature_c']}°C ({weather_info['temperature_f']}°F)")
    print(f"体感温度: {weather_info['feels_like_c']}°C")
    print(f"天气状况: {weather_info['weather_description']}")
    print(f"湿度: {weather_info['humidity']}%")
    print(f"风速: {weather_info['wind_speed']} km/h")
    print(f"风向: {weather_info['wind_direction']}")
    print("=" * 50)

def main():
    """
    主函数：处理命令行参数并获取天气信息
    """
    # 获取命令行参数
    if len(sys.argv) > 1:
        city = sys.argv[1]
    else:
        # 如果没有提供城市参数，使用默认值
        city = "Beijing"
        print(f"未指定城市，使用默认城市: {city}")
    
    print(f"正在获取 {city} 的天气信息...")
    
    # 获取天气信息
    weather_info = get_weather(city)
    
    # 打印天气信息
    if weather_info:
        print_weather_info(weather_info)
    else:
        print("获取天气信息失败")

if __name__ == "__main__":
    main()