#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

def main():
    # 获取当前日期时间
    current_time = datetime.datetime.now()
    
    # 格式化日期时间
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    # 打印问候和日期时间
    print("=" * 40)
    print("Hello from GGbot!")
    print(f"Current date and time: {formatted_time}")
    print("This is a test Python script.")
    print("=" * 40)
    
    # 添加一些额外的信息
    print(f"\nAdditional info:")
    print(f"  Year: {current_time.year}")
    print(f"  Month: {current_time.month}")
    print(f"  Day: {current_time.day}")
    print(f"  Day of week: {current_time.strftime('%A')}")
    print(f"  Hour: {current_time.hour}")
    print(f"  Minute: {current_time.minute}")
    print(f"  Second: {current_time.second}")

if __name__ == "__main__":
    main()