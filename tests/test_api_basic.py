"""API基本功能测试"""

import sys
import os
from unittest.mock import MagicMock
from pathlib import Path
import pytest

from ggbot.app.app_bootstrap import AgentRuntime
# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.unit
def test_api_module_import():
    """测试API模块导入"""
    try:
        from ggbot.api import __version__, create_api_server
        print(f"[OK] API模块导入成功，版本: {__version__}")
    except ImportError as e:
        pytest.fail(f"API模块导入失败: {e}")


@pytest.mark.unit
def test_api_server_creation():
    """测试API服务器创建"""
    try:
        # 模拟运行时
        runtime = MagicMock(spec=AgentRuntime)
        settings = MagicMock()
        settings.resolved_transcript_dir.return_value = Path(".ggbot/transcripts")
        runtime.settings = settings
        runtime.session_id = "test_session"

        from ggbot.api.server import create_api_server
        server = create_api_server(runtime, host="127.0.0.1", port=8000)

        print(f"[OK] API服务器创建成功")
        print(f"   主机: {server.host}")
        print(f"   端口: {server.port}")
        print(f"   应用标题: {server.app.title}")

        # 检查路由
        routes = [getattr(route, "path", "") for route in server.app.routes]
        expected_routes = ["/", "/api/v1/health", "/api/v1/config", "/api/v1/sessions", "/ws"]
        for route in expected_routes:
            exists = route in routes or any(route in str(getattr(r, "path", "")) for r in server.app.routes)
            print(f"   路由 {route}: {'[OK] 存在' if exists else '[ERROR] 缺失'}")
            assert exists, f"路由缺失: {route}"

    except Exception as e:
        pytest.fail(f"API服务器创建失败: {e}")


@pytest.mark.unit
def test_data_models():
    """测试数据模型"""
    try:
        from ggbot.api.server import (
            MessageRequest, ToolExecuteRequest, SessionCreateRequest,
            SessionUpdateRequest, ConfigUpdateRequest, WebSocketMessage
        )

        # 测试MessageRequest
        msg_request = MessageRequest(content="测试消息")
        assert msg_request.content == "测试消息"
        print("[OK] MessageRequest 模型测试通过")

        # 测试ToolExecuteRequest
        tool_request = ToolExecuteRequest(
            name="test_tool",
            arguments={"param": "value"},
            session_id="test_session"
        )
        assert tool_request.name == "test_tool"
        print("[OK] ToolExecuteRequest 模型测试通过")

        # 测试SessionCreateRequest
        session_create = SessionCreateRequest(type="chat", title="测试会话")
        assert session_create.type == "chat"
        print("[OK] SessionCreateRequest 模型测试通过")

        # 测试ConfigUpdateRequest
        config_update = ConfigUpdateRequest(openai_model="gpt-4-turbo", max_turns=10)
        assert config_update.openai_model == "gpt-4-turbo"
        print("[OK] ConfigUpdateRequest 模型测试通过")

        # 测试WebSocketMessage
        ws_message = WebSocketMessage(type="command", payload={"test": "data"})
        assert ws_message.type == "command"
        print("[OK] WebSocketMessage 模型测试通过")

    except Exception as e:
        pytest.fail(f"数据模型测试失败: {e}")


@pytest.mark.unit
def test_services_module():
    """测试服务模块"""
    try:
        from ggbot.api.services import APIService, EventsCollector
        from ggbot.api.session_runtime_manager import SessionRuntimeManager
        from ggbot.state.transcript import Transcript
        from ggbot.models.protocol_models import ChatMessage

        # 测试EventsCollector
        collector = EventsCollector()
        collector.add_assistant_delta("Hello")
        collector.add_assistant_final("Hello World")
        collector.add_thinking({"thinking": "I'm thinking"})

        events = collector.get_events()
        assert len(events) == 3
        assert collector.has_thinking is True
        assert collector.get_final_response() == "Hello"

        print("[OK] EventsCollector 测试通过")

        # 测试APIService（主线接口：AgentRuntime + registry.specs/call）
        runtime = MagicMock(spec=AgentRuntime)
        settings = MagicMock()
        settings.resolved_transcript_dir.return_value = Path(".ggbot/transcripts")
        settings.workspace_root = Path(".")
        settings.openai_model = "gpt-4.1-mini"
        settings.max_turns = 8
        settings.max_tool_calls = 30
        settings.max_tool_calls_per_tool = 12
        settings.max_tool_calls_same_args = 3
        settings.thinking_enabled = False
        settings.shell_confirm = True
        runtime.settings = settings
        runtime.session_id = "test_session"
        runtime.client = MagicMock()
        runtime.registry = MagicMock()
        runtime.registry.specs.return_value = []
        runtime.registry.call.return_value = "Tool result"
        runtime.transcript = MagicMock()
        runtime.messages = []

        service = APIService(runtime)

        print("[OK] APIService 创建成功")
        assert service is not None
        service.close()

        # 测试 SessionRuntimeManager 隔离不同会话上下文
        runtime.transcript = Transcript(path=Path(".ggbot/transcripts/test_session.jsonl"))
        runtime.messages = [ChatMessage(role="system", content="sys")]
        runtime.system_message = ChatMessage(role="system", content="sys")
        manager = SessionRuntimeManager(runtime)
        context_a = manager.get_or_create_context("test_session")
        context_b = manager.get_or_create_context("other_session")
        assert context_a.session_id == "test_session"
        assert context_b.session_id == "other_session"
        assert context_a is not context_b
        print("[OK] SessionRuntimeManager 测试通过")

    except Exception as e:
        pytest.fail(f"服务模块测试失败: {e}")


@pytest.mark.unit
def test_cli_command():
    """测试CLI命令"""
    try:
        from ggbot.command import app

        # 检查api命令是否注册
        command_names = [command.name for command in app.registered_commands]
        callback_names = [getattr(command.callback, "__name__", "") for command in app.registered_commands]
        has_api_command = ("api" in command_names) or ("api" in callback_names)
        print("[OK] CLI api命令已注册" if has_api_command else "[ERROR] CLI api命令未注册")
        assert has_api_command, "CLI api命令未注册"

    except Exception as e:
        pytest.fail(f"CLI命令测试失败: {e}")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("GGbot API基本功能测试")
    print("=" * 60)

    tests = [
        ("API模块导入", test_api_module_import),
        ("数据模型", test_data_models),
        ("服务模块", test_services_module),
        ("CLI命令", test_cli_command),
        ("API服务器创建", test_api_server_creation),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n[{name}]")
        try:
            test_func()
            success = True
            status = "[OK] 通过"
            print(f"   结果: {status}")
            results.append((name, success))
        except Exception as e:
            print(f"   异常: {e}")
            print(f"   结果: [ERROR] 异常")
            results.append((name, False))

    # 打印摘要
    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"通过: {passed}/{total}")

    for name, success in results:
        status = "[OK]" if success else "[ERROR]"
        print(f"  {status} {name}")

    if passed == total:
        print("\n[SUCCESS] 所有基本功能测试通过!")
        print("\n下一步:")
        print("  1. 依赖已安装: fastapi uvicorn websockets")
        print("  2. 启动API服务器: python -m ggbot api")
        print("  3. 运行完整测试: python -m pytest tests/test_api.py -v")
        print("  4. 运行示例: python examples/api_example.py")
        return True
    else:
        print("\n[WARNING] 部分测试失败，请检查问题")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
