"""API集成测试"""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ggbot.api.server import APIServer, create_api_server
from ggbot.app.app_bootstrap import AgentRuntime
from ggbot.app.config import Settings
from ggbot.api.permission_manager import get_permission_manager
from ggbot.models.protocol_models import ChatMessage
from ggbot.state.transcript import Transcript


def _ws_command(client: TestClient, command: str, payload: dict):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "command",
                "id": "test_cmd",
                "command": command,
                "payload": payload,
            }
        )
        messages = []
        while True:
            message = websocket.receive_json()
            messages.append(message)
            if message["type"] in {"response", "error"}:
                return messages


@pytest.fixture
def mock_runtime():
    """创建模拟的运行时"""
    runtime = MagicMock(spec=AgentRuntime)
    transcript_dir = Path(tempfile.mkdtemp())

    # 模拟设置
    settings = MagicMock(spec=Settings)
    settings.openai_model = "gpt-4.1-mini"
    settings.openai_api_key = "test-key"
    settings.openai_base_url = "https://api.openai.com/v1"
    settings.workspace_root = Path(".")
    settings.max_turns = 8
    settings.max_tool_calls = 30
    settings.max_tool_calls_per_tool = 12
    settings.max_tool_calls_same_args = 3
    settings.thinking_enabled = False
    settings.shell_confirm = True
    settings.resolved_transcript_dir.return_value = transcript_dir

    runtime.settings = settings
    runtime.session_id = "test_session_123"
    runtime.messages = []
    runtime.transcript = Transcript(path=transcript_dir / "test_session_123.jsonl")
    runtime.system_message = ChatMessage(role="system", content="sys")
    runtime.client = MagicMock()
    runtime.registry = MagicMock()

    # 模拟工具注册表
    runtime.registry.list_tools.return_value = ["file_read", "shell_run"]
    runtime.registry.get_tool.return_value = MagicMock(
        description="Test tool",
        input_model=None,
        requires_context=False,
        function=MagicMock(return_value="Tool executed successfully")
    )

    return runtime


@pytest.fixture
def api_server(mock_runtime):
    """创建API服务器实例"""
    return create_api_server(mock_runtime, host="127.0.0.1", port=8000)


@pytest.fixture
def test_client(api_server):
    """创建测试客户端"""
    return TestClient(api_server.app)


class TestAPIServer:
    """API服务器测试"""

    def test_root_endpoint(self, test_client):
        """测试根端点"""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "GGbot API"
        assert data["version"] == "0.1.0"
        assert data["status"] == "running"

    def test_health_endpoint(self, test_client):
        """测试健康检查端点"""
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_get_config(self, test_client, mock_runtime):
        """测试获取配置"""
        response = test_client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()

        assert data["openai_model"] == mock_runtime.settings.openai_model
        assert data["workspace_root"] == str(mock_runtime.settings.workspace_root)
        assert data["session_id"] == mock_runtime.session_id
        assert "has_openai_api_key" in data

    def test_list_sessions(self, test_client):
        """测试获取会话列表"""
        response = test_client.get("/api/v1/sessions")
        assert response.status_code == 200
        data = response.json()

        assert "current_session_id" in data
        assert "default_sessions" in data
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_create_session(self, test_client):
        """测试创建会话"""
        payload = {
            "type": "chat",
            "title": "测试会话"
        }
        response = test_client.post("/api/v1/sessions", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "id" in data
        assert data["title"] == "测试会话"
        assert data["type"] == "chat"
        assert "created_at" in data

    def test_list_tools(self, test_client, mock_runtime):
        """测试获取工具列表"""
        response = test_client.get("/api/v1/tools")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2  # 模拟返回2个工具
        assert len(data["tools"]) == 2
        assert data["tools"][0]["name"] == "file_read"

    @pytest.mark.asyncio
    async def test_send_message_success(self, test_client, mock_runtime):
        """测试成功发送消息"""
        # 模拟成功的查询结果
        mock_result = MagicMock()
        mock_result.turns_used = 1
        mock_result.events = []

        with (
            patch('ggbot.api.services.run_query', return_value=mock_result),
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "content": "测试消息",
                    "max_turns": 2,
                    "thinking_enabled": False,
                },
            )
            response = messages[-1]

            assert response["type"] == "response"
            data = response["payload"]
            assert data["success"] is True
            assert data["session_id"] == mock_runtime.session_id
            assert data["turn_number"] == 1
            assert data["turns_used"] == 1

    @pytest.mark.asyncio
    async def test_send_message_emits_session_update_when_title_generated(self, test_client, mock_runtime):
        """测试首轮生成标题后会发出 session_update 事件。"""
        mock_result = MagicMock()
        mock_result.turns_used = 1
        mock_result.events = []

        with (
            patch('ggbot.api.services.run_query', return_value=mock_result),
            patch('ggbot.api.services.APIService._generate_title', return_value="测试标题"),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "content": "请生成标题",
                    "max_turns": 2,
                    "thinking_enabled": False,
                },
            )
            response = messages[-1]

        assert response["type"] == "response"
        payload = response["payload"]
        assert payload["success"] is True
        assert payload["title"] == "测试标题"
        assert any(
            event.get("type") == "session_update" and event.get("data", {}).get("title") == "测试标题"
            for event in payload.get("events", [])
        )

    @pytest.mark.asyncio
    async def test_send_message_failure(self, test_client, mock_runtime):
        """测试发送消息失败"""
        # 模拟失败的查询
        with (
            patch('ggbot.api.services.run_query', side_effect=Exception("API错误")),
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "content": "测试消息",
                    "max_turns": 2,
                },
            )
            response = messages[-1]
            assert response["type"] == "error"
            assert "API错误" in response["message"]

    def test_get_recent_events(self, test_client):
        """测试获取最近事件"""
        response = test_client.get("/api/v1/events?limit=10")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "limit" in data
        assert "events" in data
        assert data["limit"] == 10
        assert isinstance(data["events"], list)

    def test_get_recent_events_reflects_runtime_event_stream(self, test_client, mock_runtime):
        """测试最近事件来自主执行事件流，而不是全局总线旁路。"""
        mock_result = MagicMock()
        mock_result.turns_used = 1

        def fake_run_query(*args, **kwargs):
            event_callback = kwargs["event_callback"]
            from ggbot.events.runtime_events import runtime_event

            event_callback(runtime_event("turn_update", {"current_turn": 1, "max_turns": 2}))
            event_callback(runtime_event("tool_call", {"id": "call_1", "name": "echo", "arguments": {"text": "hi"}}))
            return mock_result

        with (
            patch('ggbot.api.services.run_query', side_effect=fake_run_query),
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "content": "测试消息",
                    "max_turns": 2,
                },
            )
            assert messages[-1]["type"] == "response"

        events_response = test_client.get("/api/v1/events?limit=10")
        assert events_response.status_code == 200
        payload = events_response.json()
        event_types = [event["type"] for event in payload["events"]]
        assert "turn_update" in event_types
        assert "tool_call" in event_types

    @pytest.mark.asyncio
    async def test_switch_session_then_permission_events_write_to_current_transcript(self, api_server, mock_runtime):
        """测试切换会话后，权限事件写入当前会话 transcript。"""
        service = api_server.api_service
        original_session = mock_runtime.session_id

        switched = await service.create_session(title="新会话")
        new_session_id = switched["id"]
        await service.switch_session(new_session_id)
        current_context = service._get_or_create_session_context(new_session_id)

        emitted = []
        manager = get_permission_manager()
        token = manager.set_request_context(
            connection_id="conn-1",
            session_id=new_session_id,
            event_callback=lambda event: emitted.append(event),
            transcript=current_context.transcript,
        )
        try:
            result_holder = {}

            def worker():
                inner_token = manager.set_request_context(
                    connection_id="conn-1",
                    session_id=new_session_id,
                    event_callback=lambda event: emitted.append(event),
                    transcript=current_context.transcript,
                )
                try:
                    allowed, reason, request_id = manager.request(
                        tool_name="shell_run",
                        arguments={"command": "echo hi"},
                        timeout_s=1.0,
                    )
                    result_holder["allowed"] = allowed
                    result_holder["reason"] = reason
                    result_holder["request_id"] = request_id
                finally:
                    manager.reset_request_context(inner_token)

            import threading

            thread = threading.Thread(target=worker)
            thread.start()

            deadline = time.time() + 1.0
            request_id = None
            while time.time() < deadline:
                for event in emitted:
                    if event.type == "permission_request":
                        request_id = event.data["request_id"]
                        break
                if request_id:
                    break
                time.sleep(0.01)

            assert request_id is not None
            assert manager.resolve(
                request_id=request_id,
                allowed=True,
                reason="approved",
                actor_connection_id="conn-1",
                actor_session_id=new_session_id,
            ) is True
            thread.join(timeout=2.0)
        finally:
            manager.reset_request_context(token)

        original_path = service.session_store.transcript_dir / f"{original_session}.jsonl"
        new_path = service.session_store.transcript_dir / f"{new_session_id}.jsonl"

        old_text = original_path.read_text(encoding="utf-8") if original_path.exists() else ""
        new_text = new_path.read_text(encoding="utf-8")
        assert "permission_request" not in old_text
        assert "permission_response" not in old_text
        assert "permission_request" in new_text
        assert "permission_response" in new_text

    @pytest.mark.asyncio
    async def test_switch_session_does_not_mutate_global_runtime_state(self, api_server, mock_runtime):
        """测试切换会话只改变 APIService 当前会话，不修改共享 runtime.session_id。"""
        service = api_server.api_service
        original_runtime_session_id = mock_runtime.session_id

        switched = await service.create_session(title="隔离会话")
        new_session_id = switched["id"]
        result = await service.switch_session(new_session_id)

        assert result["current_session_id"] == new_session_id
        assert service.current_session_id == new_session_id
        assert mock_runtime.session_id == original_runtime_session_id

    def test_update_config(self, test_client, mock_runtime):
        """测试更新配置"""
        payload = {
            "openai_model": "gpt-4-turbo",
            "max_turns": 10,
            "thinking_enabled": True
        }
        response = test_client.put("/api/v1/config", json=payload)
        assert response.status_code == 200
        data = response.json()

        # 验证配置已更新
        assert data["openai_model"] == "gpt-4-turbo"
        assert data["max_turns"] == 10
        assert data["thinking_enabled"] is True

    def test_invalid_session_id(self, test_client):
        """测试无效的会话ID"""
        response = test_client.get("/api/v1/sessions/nonexistent")
        assert response.status_code == 404

    def test_missing_required_field(self, test_client):
        """测试WS命令缺少 content 时退化为默认空字符串。"""
        mock_result = MagicMock()
        mock_result.turns_used = 1
        mock_result.events = []
        with (
            patch('ggbot.api.services.run_query', return_value=mock_result),
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "max_turns": 2,
                },
            )
        response = messages[-1]
        assert response["type"] == "response"
        assert response["payload"]["success"] is True

    def test_cors_headers(self, test_client):
        """测试CORS头部"""
        response = test_client.options("/api/v1/health")
        assert response.status_code == 200
        # 检查CORS头部
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"

    def test_schedule_event_delivery_uses_loop_threadsafe(self, api_server):
        """测试事件转发通过 loop.call_soon_threadsafe 调度"""

        class FakeLoop:
            def __init__(self):
                self.called = False
                self.callback = None

            def call_soon_threadsafe(self, cb):
                self.called = True
                self.callback = cb

        fake_loop = FakeLoop()

        event = MagicMock()
        event.type = "status"
        event.data = {"message": "ok"}
        event.source = "test"

        api_server._schedule_event_delivery(fake_loop, "cid", event)

        assert fake_loop.called is True
        assert callable(fake_loop.callback)

    def test_schedule_event_delivery_ignores_closed_loop(self, api_server):
        """测试事件循环关闭时不抛异常"""

        class ClosedLoop:
            def call_soon_threadsafe(self, cb):
                raise RuntimeError("loop closed")

        event = MagicMock()
        event.type = "status"
        event.data = {"message": "ok"}
        event.source = "test"

        # Should not raise.
        api_server._schedule_event_delivery(ClosedLoop(), "cid", event)


class TestWebSocket:
    """WebSocket测试"""

    @pytest.mark.asyncio
    async def test_websocket_connection(self, api_server):
        """测试WebSocket连接"""
        # 使用TestClient测试WebSocket
        with TestClient(api_server.app) as client:
            with client.websocket_connect("/ws") as websocket:
                # 连接应该成功
                assert websocket is not None

                # 可以发送和接收消息
                test_message = {
                    "type": "command",
                    "id": "test_1",
                    "command": "get_config",
                    "payload": {}
                }
                websocket.send_json(test_message)

                # 接收响应
                response = websocket.receive_json()
                assert response["type"] == "response"
                assert response["id"] == "test_1"
                assert response["command"] == "get_config"

    @pytest.mark.asyncio
    async def test_websocket_invalid_message(self, api_server):
        """测试无效的WebSocket消息"""
        with TestClient(api_server.app) as client:
            with client.websocket_connect("/ws") as websocket:
                # 发送无效消息
                websocket.send_json({"type": "invalid"})

                # 应该收到错误响应
                response = websocket.receive_json()
                assert response["type"] == "error"
                assert "message" in response

class TestErrorHandling:
    """错误处理测试"""

    def test_server_initialization_error(self):
        """测试服务器初始化错误"""
        # 使用无效的运行时
        with pytest.raises(Exception):
            create_api_server(None)  # type: ignore[arg-type]

    def test_invalid_json_payload(self, test_client):
        """测试无效的WS命令类型"""
        with TestClient(test_client.app) as client:
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "oops"})
                response = websocket.receive_json()
                assert response["type"] == "error"

    def test_rate_limiting(self, test_client):
        """测试速率限制（如果实现）"""
        # 连续发送多个请求
        for i in range(10):
            response = test_client.get("/api/v1/health")
            assert response.status_code == 200  # 应该都成功

    def test_large_payload(self, test_client):
        """测试大负载"""
        large_content = "A" * 10000  # 10KB的文本
        mock_result = MagicMock()
        mock_result.turns_used = 1
        mock_result.events = []
        with (
            patch('ggbot.api.services.run_query', return_value=mock_result),
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            messages = _ws_command(
                test_client,
                "send_message",
                {
                    "content": large_content,
                    "max_turns": 1,
                },
            )
        response = messages[-1]
        assert response["type"] in ["response", "error"]


@pytest.mark.integration
class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, test_client, mock_runtime):
        """测试完整工作流程"""
        # 1. 获取配置
        config_response = test_client.get("/api/v1/config")
        assert config_response.status_code == 200

        # 2. 创建新会话
        session_response = test_client.post("/api/v1/sessions", json={
            "type": "chat",
            "title": "集成测试会话"
        })
        assert session_response.status_code == 200
        session_data = session_response.json()
        session_id = session_data["id"]

        # 3. 发送消息
        with (
            patch('ggbot.api.services.run_query') as mock_run_query,
            patch('ggbot.api.services.APIService._generate_title', return_value=None),
        ):
            mock_result = MagicMock()
            mock_result.turns_used = 1
            mock_result.events = []
            mock_run_query.return_value = mock_result

            responses = _ws_command(
                test_client,
                "send_message",
                {
                    "content": "集成测试消息",
                    "session_id": session_id,
                    "max_turns": 1,
                },
            )
            assert responses[-1]["type"] == "response"
            message_data = responses[-1]["payload"]
            assert message_data["success"] is True

        # 4. 获取会话详情
        session_detail_response = test_client.get(f"/api/v1/sessions/{session_id}")
        assert session_detail_response.status_code == 200
        session_detail = session_detail_response.json()
        assert session_detail["id"] == session_id
        assert session_detail["title"] == "集成测试会话"

        # 5. 获取工具列表
        tools_response = test_client.get("/api/v1/tools")
        assert tools_response.status_code == 200

        # 6. 获取最近事件
        events_response = test_client.get("/api/v1/events?limit=5")
        assert events_response.status_code == 200


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v"])
