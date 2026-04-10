import time
import winsound
import datetime

print("⏰ 闹钟已设置，将在10分钟后提醒...")
print(f"开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 等待10分钟（600秒）
time.sleep(600)

# 闹钟时间到
print("\n" + "="*50)
print("⏰ 闹钟时间到了！")
print(f"现在时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("闹钟提醒：10分钟时间到了！")
print("="*50)

# 发出蜂鸣声（频率1000Hz，持续1000ms）
for i in range(5):
    winsound.Beep(1000, 500)
    time.sleep(0.5)