"""演示如何使用 log --follow --events 监听TUI事件"""

import subprocess
import time
import threading
import sys
import os

def run_tui_demo():
    """运行TUI演示（模拟）"""
    print("启动TUI演示...")

    # 模拟TUI启动并产生一些事件
    from ggbot.core.domain import RuntimeEvent
    from ggbot.core.event_bus import publish_event

    # 这些事件会被记录到转录日志
    events = [
        RuntimeEvent(type="session_start", data={"id": "demo_123"}),
        RuntimeEvent(type="status", data={"message": "TUI启动", "severity": "info"}),
        RuntimeEvent(type="assistant_delta", data={"delta": "Hello"}),
        RuntimeEvent(type="assistant_final", data={"content": "Hello World!"}),
        RuntimeEvent(type="thinking", data={"thinking": "思考中..."}),
    ]

    for event in events:
        print(f"[TUI] 产生事件: {event.type}")
        publish_event(event)
        time.sleep(1)

    print("TUI演示完成")

def test_log_follow():
    """测试 log --follow --events 命令"""
    print("\n测试 log --follow --events...")

    # 先清理可能存在的旧转录文件
    from ggbot.core.runtime import create_app_session
    app_session = create_app_session(default_session_name="test")
    transcript_path = app_session.transcript.path

    if transcript_path.exists():
        print(f"清理旧转录文件: {transcript_path}")
        transcript_path.unlink()

    # 启动log命令（5秒后超时）
    cmd = [sys.executable, "-m", "ggbot", "log", "--follow", "--events", "--poll-ms", "100"]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1
        )

        # 给log命令一点时间启动
        time.sleep(1)

        # 在后台线程中运行TUI演示
        tui_thread = threading.Thread(target=run_tui_demo, daemon=True)
        tui_thread.start()

        # 读取log命令输出（5秒）
        start_time = time.time()
        while time.time() - start_time < 5:
            line = process.stdout.readline()
            if line:
                print(f"[LOG] {line.strip()}")

        # 清理
        process.terminate()
        tui_thread.join(timeout=2)

        print("\n测试完成！")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("演示：使用 log --follow --events 监听TUI事件")
    print("=" * 60)

    test_log_follow()

    print("\n" + "=" * 60)
    print("总结：")
    print("1. TUI的所有事件都记录到转录日志")
    print("2. log --follow --events 可以实时监听这些事件")
    print("3. 支持跨进程监听（因为通过文件系统）")
    print("=" * 60)