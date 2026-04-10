#!/usr/bin/env python3
import time
import sys
import os

def set_reminder(minutes=10, message="时间到了！"):
    """设置一个定时提醒"""
    seconds = minutes * 60
    print(f"[闹钟] 已设置 {minutes} 分钟后的提醒...")
    print(f"[消息] 提醒内容: {message}")
    print("等待中...")
    
    time.sleep(seconds)
    
    # 尝试发送通知（跨平台）
    try:
        if sys.platform == "darwin":  # macOS
            # 使用不同的引号嵌套方式
            cmd = f'''osascript -e 'display notification "{message}" with title "提醒"' '''
            os.system(cmd)
        elif sys.platform == "win32":  # Windows
            os.system(f'msg * "{message}"')
        else:  # Linux
            os.system(f'notify-send "提醒" "{message}"')
    except:
        pass
    
    # 终端提醒
    print("\n" + "="*50)
    print(f"[提醒] {message}")
    print("="*50)

if __name__ == "__main__":
    # 默认10分钟后提醒
    set_reminder(10, "10分钟时间到！")