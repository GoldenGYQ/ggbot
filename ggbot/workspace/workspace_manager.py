from __future__ import annotations

from pathlib import Path
from typing import Set
import json


class WorkspaceManager:
    """管理工作区，限制脚本执行只能在允许的工作区内"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.allowed_workspaces: Set[Path] = {self.workspace_root}
        self.config_file = (Path.home() / ".ggbot" / "allowed_workspaces.json").resolve()

        # 加载已保存的允许工作区
        self._load_allowed_workspaces()

    def _load_allowed_workspaces(self) -> None:
        """从配置文件加载允许的工作区"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    key = str(self.workspace_root)
                    all_mappings = data.get("workspace_roots", {})
                    raw_list = []
                    if isinstance(all_mappings, dict) and isinstance(all_mappings.get(key), list):
                        raw_list = all_mappings.get(key, [])
                    elif isinstance(data.get("allowed_workspaces"), list):
                        # Legacy file format fallback.
                        raw_list = data.get("allowed_workspaces", [])

                    for path_str in raw_list:
                        raw_path = Path(path_str)
                        path = (raw_path if raw_path.is_absolute() else (self.workspace_root / raw_path)).resolve()
                        # 只加载在workspace_root下的工作区
                        try:
                            path.relative_to(self.workspace_root)
                            self.allowed_workspaces.add(path)
                        except ValueError:
                            # 忽略不在workspace_root下的路径
                            pass
            except (json.JSONDecodeError, IOError):
                # 如果配置文件损坏，使用默认设置
                pass

    def _save_allowed_workspaces(self) -> None:
        """保存允许的工作区到配置文件"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, object]
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}

        mappings = data.get("workspace_roots")
        if not isinstance(mappings, dict):
            mappings = {}
        mappings[str(self.workspace_root)] = [
            str(path.relative_to(self.workspace_root))
            if path != self.workspace_root else "."
            for path in self.allowed_workspaces
        ]
        data["workspace_roots"] = mappings

        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_allowed_workspace(self, path: Path) -> Path:
        """添加允许的工作区"""
        resolved_path = path.resolve()

        # 确保路径在workspace_root下
        try:
            resolved_path.relative_to(self.workspace_root)
        except ValueError as e:
            raise PermissionError(
                f"工作区必须在 {self.workspace_root} 下: {resolved_path}"
            ) from e

        # 确保路径存在
        resolved_path.mkdir(parents=True, exist_ok=True)

        self.allowed_workspaces.add(resolved_path)
        self._save_allowed_workspaces()
        return resolved_path

    def remove_allowed_workspace(self, path: Path) -> bool:
        """移除允许的工作区（不能移除根工作区）"""
        resolved_path = path.resolve()

        if resolved_path == self.workspace_root:
            raise PermissionError("不能移除根工作区")

        if resolved_path in self.allowed_workspaces:
            self.allowed_workspaces.remove(resolved_path)
            self._save_allowed_workspaces()
            return True
        return False

    def is_allowed_workspace(self, path: Path) -> bool:
        """检查路径是否在允许的工作区内"""
        resolved_path = path.resolve()

        # 检查路径是否在允许的工作区内或其子目录中
        for allowed_path in self.allowed_workspaces:
            try:
                resolved_path.relative_to(allowed_path)
                # 路径在允许的工作区内或其子目录中
                return True
            except ValueError:
                continue

        return False

    def get_allowed_workspaces(self) -> list[Path]:
        """获取所有允许的工作区（按路径排序）"""
        return sorted(self.allowed_workspaces, key=lambda p: str(p))

    def get_relative_paths(self) -> list[str]:
        """获取相对路径表示"""
        return [
            str(path.relative_to(self.workspace_root))
            if path != self.workspace_root else "."
            for path in self.get_allowed_workspaces()
        ]

    def ensure_in_allowed_workspace(self, path: Path) -> Path:
        """确保路径在允许的工作区内，否则抛出异常"""
        resolved_path = path.resolve()

        if not self.is_allowed_workspace(resolved_path):
            allowed_paths = self.get_relative_paths()
            raise PermissionError(
                f"路径不在允许的工作区内: {resolved_path}\n"
                f"允许的工作区: {', '.join(allowed_paths)}"
            )

        return resolved_path

    def create_sub_workspace(self, relative_path: str) -> Path:
        """创建子工作区并添加到允许列表"""
        sub_path = self.workspace_root / relative_path
        return self.add_allowed_workspace(sub_path)


class PermissionError(Exception):
    """权限错误"""
    pass


# 全局工作区管理器实例
_workspace_manager: WorkspaceManager | None = None


def init_workspace_manager(workspace_root: Path) -> WorkspaceManager:
    """初始化全局工作区管理器"""
    global _workspace_manager
    _workspace_manager = WorkspaceManager(workspace_root)
    return _workspace_manager


def get_workspace_manager() -> WorkspaceManager:
    """获取全局工作区管理器"""
    if _workspace_manager is None:
        raise RuntimeError("工作区管理器未初始化")
    return _workspace_manager
