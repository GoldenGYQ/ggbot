#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试工作区限制功能"""

import tempfile
import shutil
from pathlib import Path
import sys
import os

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from ggbot.core.workspace_manager import WorkspaceManager, init_workspace_manager, get_workspace_manager


def test_workspace_manager():
    """测试工作区管理器"""
    print("=== 测试工作区管理器 ===")

    # 创建临时目录作为workspace_root
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir) / "test_workspace"
        workspace_root.mkdir(parents=True)

        print(f"工作区根目录: {workspace_root}")

        # 初始化工作区管理器
        manager = init_workspace_manager(workspace_root)

        # 测试1: 初始状态
        print("\n1. 测试初始状态:")
        allowed = manager.get_allowed_workspaces()
        print(f"  允许的工作区: {[str(p) for p in allowed]}")

        # 测试2: 添加工作区
        print("\n2. 测试添加工作区:")
        sub_workspace = workspace_root / "project1"
        manager.add_allowed_workspace(sub_workspace)
        print(f"  添加工作区: {sub_workspace}")

        # 测试3: 检查工作区
        print("\n3. 测试工作区检查:")
        test_paths = [
            (workspace_root / "project1", True, "project1根目录"),
            (workspace_root / "project1" / "src", True, "project1子目录"),
            (workspace_root / "project2", True, "未添加的project2（在根工作区内）"),
            (workspace_root / ".." / "outside", False, "工作区外的目录"),
        ]

        for path, expected, description in test_paths:
            is_allowed = manager.is_allowed_workspace(path)
            status = "[通过]" if is_allowed == expected else "[失败]"
            print(f"  {status} {description}: {path} -> 允许={is_allowed} (期望={expected})")

        # 测试4: 创建子工作区
        print("\n4. 测试创建子工作区:")
        sub_workspace2 = manager.create_sub_workspace("project2/subdir")
        print(f"  创建子工作区: {sub_workspace2}")

        # 测试5: 获取相对路径
        print("\n5. 测试相对路径:")
        relative_paths = manager.get_relative_paths()
        print(f"  相对路径: {relative_paths}")

        # 测试6: 确保路径在允许工作区内
        print("\n6. 测试路径验证:")
        try:
            allowed_path = manager.ensure_in_allowed_workspace(workspace_root / "project1" / "src")
            print(f"  [通过] 允许的路径: {allowed_path}")
        except Exception as e:
            print(f"  [失败] 错误: {e}")

        try:
            allowed_path = manager.ensure_in_allowed_workspace(workspace_root / "not_allowed")
            print(f"  [通过] 允许的路径（在根工作区内）: {allowed_path}")
        except Exception as e:
            print(f"  [失败] 错误: {e}")

        # 测试7: 配置文件
        print("\n7. 测试配置文件:")
        config_file = workspace_root / ".ggbot" / "allowed_workspaces.json"
        if config_file.exists():
            print(f"  [通过] 配置文件存在: {config_file}")
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"  配置内容: {content[:200]}...")
        else:
            print(f"  [失败] 配置文件不存在")

    print("\n=== 所有测试完成 ===")


def test_shell_command_validation():
    """测试shell命令验证"""
    print("\n=== 测试shell命令验证 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir) / "test_shell"
        workspace_root.mkdir(parents=True)

        # 初始化工作区管理器
        manager = init_workspace_manager(workspace_root)

        # 添加一些工作区
        manager.add_allowed_workspace(workspace_root / "allowed_project")
        (workspace_root / "not_allowed_project").mkdir()

        # 导入验证函数
        from ggbot.tools.shell_tool import _extract_paths_from_command, _validate_command_paths

        test_commands = [
            ("cd allowed_project && ls", True, "允许的工作区"),
            ("cd not_allowed_project && ls", True, "未允许的工作区（在根工作区内）"),
            ("ls /tmp", False, "系统目录"),
            ("echo 'hello' > test.txt", True, "当前工作区"),
            ("cat ../outside.txt", False, "上级目录"),
            ("python script.py", True, "无路径命令"),
        ]

        for command, should_pass, description in test_commands:
            print(f"\n测试: {description}")
            print(f"  命令: {command}")
            try:
                _validate_command_paths(command, workspace_root)
                if should_pass:
                    print(f"  [通过] 通过验证 (符合预期)")
                else:
                    print(f"  [失败] 应该失败但通过了")
            except Exception as e:
                if not should_pass:
                    print(f"  [通过] 正确拒绝: {e}")
                else:
                    print(f"  [失败] 应该通过但失败了: {e}")

    print("\n=== shell命令验证测试完成 ===")


if __name__ == "__main__":
    test_workspace_manager()
    test_shell_command_validation()