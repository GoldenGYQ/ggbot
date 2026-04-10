#!/bin/bash
echo -e '\a'  # 系统蜂鸣声
echo '⏰ 闹钟时间到了！现在是 $(date)'
echo '闹钟提醒：10分钟时间到了！'
# 如果有notify-send命令，可以发送桌面通知
if command -v notify-send &> /dev/null; then
    notify-send "⏰ 闹钟提醒" "10分钟时间到了！现在是 $(date)"
fi