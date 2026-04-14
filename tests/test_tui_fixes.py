"""测试TUI修复"""

import sys
import time

def test_stream_delta_logic():
    """测试流式输出逻辑"""
    print("测试流式输出逻辑...")

    # 模拟流式输出
    test_deltas = [
        "Hello", " ", "world", "!", " ",
        "This", " ", "is", " ", "a", " ", "test", ".",
        "\n", "New", " ", "line", "."
    ]

    buffer = ""
    updates = 0

    for delta in test_deltas:
        buffer += delta

        # 应用我们的更新逻辑
        should_update = (
            len(buffer) < 20 or
            delta.endswith(' ') or
            delta.endswith('\n') or
            delta.endswith('.') or delta.endswith(',') or
            delta.endswith('?') or delta.endswith('!')
        )

        if should_update:
            updates += 1
            clean_buffer = buffer.replace('\r', '')
            print(f"更新 {updates}: '{clean_buffer}'")

    print(f"总共 {len(test_deltas)} 个delta，{updates} 次更新")
    print(f"减少更新次数: {len(test_deltas) - updates}")

def test_log_formatting():
    """测试日志格式化"""
    print("\n测试日志格式化...")

    test_cases = [
        ("Hello\nWorld", "Hello World"),
        ("Tool\ncalls:\nread_file", "Tool calls: read_file"),
        ("Normal text", "Normal text"),
        ("", "(empty)"),
    ]

    for input_text, expected in test_cases:
        # 模拟日志渲染逻辑
        content = input_text.strip()
        if not content:
            content = "(empty)"

        # 清理换行符
        content = content.replace('\n', ' ').replace('\r', '')

        print(f"输入: '{input_text}'")
        print(f"输出: '{content}'")
        print(f"期望: '{expected}'")
        print(f"匹配: {content == expected}")
        print()

def main():
    print("=" * 60)
    print("TUI修复测试")
    print("=" * 60)

    test_stream_delta_logic()
    test_log_formatting()

    print("\n修复总结:")
    print("1. 流式输出: 减少频繁更新，只在适当时机更新显示")
    print("2. 日志格式化: 清理换行符，确保单行显示")
    print("3. 输入框: 彻底重置输入框状态")
    print("=" * 60)

if __name__ == "__main__":
    main()