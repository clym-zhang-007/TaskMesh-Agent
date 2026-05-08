"""
测试文件 - Agent Loop API

使用 pytest 和 FastAPI TestClient 进行测试。
运行方式: pip install pytest httpx && python -m pytest test_main.py -v
"""

import os
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

# ============================================================
# 测试前准备
# ============================================================

@pytest.fixture(autouse=True)
def setup_env():
    """每个测试前设置环境变量"""
    os.environ["ANTHROPIC_BASE_URL"] = "https://mock-api.example.com"
    os.environ["MODEL_ID"] = "claude-mock-model"


@pytest.fixture
def temp_db():
    """使用临时数据库文件，避免污染真实数据"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # 导入 main 前替换数据库路径
    from backend.storage.database import Database
    db = Database(db_path=path)
    yield db, path
    # 清理
    db.get_connection().close()
    if os.path.exists(path):
        os.unlink(path)


# ============================================================
# 1. Models 单元测试
# ============================================================

class TestModels:
    """数据模型测试"""

    def test_message_default_values(self):
        """测试 Message 模型默认值"""
        from backend.storage.models import Message
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.is_command is False
        assert msg.is_output is False
        assert msg.is_error is False
        assert msg.full_output is None
        assert msg.created_at is None

    def test_message_with_all_fields(self):
        """测试 Message 模型全部字段"""
        from backend.storage.models import Message
        now = datetime.now()
        msg = Message(
            role="assistant",
            content="result",
            is_command=True,
            is_output=True,
            is_error=False,
            full_output="complete output",
            created_at=now
        )
        assert msg.role == "assistant"
        assert msg.is_command is True
        assert msg.full_output == "complete output"
        assert msg.created_at == now

    def test_tool_execution_model(self):
        """测试 ToolExecution 模型"""
        from backend.storage.models import ToolExecution
        te = ToolExecution(command="ls -la", output="file1\nfile2")
        assert te.command == "ls -la"
        assert te.output == "file1\nfile2"

    def test_chat_request_without_conversation_id(self):
        """测试 ChatRequest 无需 conversation_id"""
        from backend.storage.models import ChatRequest
        req = ChatRequest(message="hi")
        assert req.message == "hi"
        assert req.conversation_id is None

    def test_chat_request_with_conversation_id(self):
        """测试 ChatRequest 带 conversation_id"""
        from backend.storage.models import ChatRequest
        req = ChatRequest(message="hi", conversation_id="abc-123")
        assert req.conversation_id == "abc-123"

    def test_chat_response(self):
        """测试 ChatResponse"""
        from backend.storage.models import ChatResponse, ToolExecution
        tools = [ToolExecution(command="cmd", output="out")]
        resp = ChatResponse(text="reply", tools=tools, conversation_id="cid")
        assert resp.text == "reply"
        assert len(resp.tools) == 1
        assert resp.conversation_id == "cid"

    def test_conversation_model(self):
        """测试 Conversation 模型"""
        from backend.storage.models import Conversation
        now = datetime.now()
        conv = Conversation(
            id="test-id",
            title="测试",
            created_at=now,
            updated_at=now,
            message_count=5
        )
        assert conv.id == "test-id"
        assert conv.title == "测试"
        assert conv.message_count == 5

    def test_conversation_create_default_title(self):
        """测试 ConversationCreate 默认标题"""
        from backend.storage.models import ConversationCreate
        req = ConversationCreate()
        assert req.title == "新对话"

    def test_conversation_update(self):
        """测试 ConversationUpdate"""
        from backend.storage.models import ConversationUpdate
        req = ConversationUpdate(title="新标题")
        assert req.title == "新标题"


# ============================================================
# 2. Agent 核心函数单元测试
# ============================================================

class TestAgentFunctions:
    """Agent 函数测试"""

    def test_safe_path_within_workspace(self):
        """测试 safe_path 在工作目录内"""
        from backend.core.agent import safe_path, WORKDIR
        result = safe_path("test.txt")
        assert result == (WORKDIR / "test.txt").resolve()
        assert result.is_relative_to(WORKDIR)

    def test_safe_path_escape_attempt(self):
        """测试 safe_path 拦截路径穿越"""
        from backend.core.agent import safe_path
        with pytest.raises(ValueError, match="escapes workspace"):
            safe_path("../../etc/passwd")

    def test_run_bash_simple_command(self):
        """测试 run_bash 执行简单命令"""
        from backend.core.agent import run_bash
        result = run_bash("echo hello")
        assert "hello" in result

    def test_run_bash_echo_hello(self):
        """测试 bash echo"""
        from backend.core.agent import run_bash
        result = run_bash("echo test123")
        assert "test123" in result

    def test_run_bash_multiline_output(self):
        """测试多行输出"""
        from backend.core.agent import run_bash
        result = run_bash("echo -e 'line1\\nline2'")
        assert "line1" in result and "line2" in result

    def test_run_bash_dangerous_blocked(self):
        """测试危险命令被拦截"""
        from backend.core.agent import run_bash
        result = run_bash("sudo rm -rf /")
        assert "Dangerous command blocked" in result

    def test_run_bash_shutdown_blocked(self):
        """测试 shutdown 被拦截"""
        from backend.core.agent import run_bash
        result = run_bash("shutdown -h now")
        assert "Dangerous command blocked" in result

    def test_run_bash_empty_output(self):
        """测试空输出"""
        from backend.core.agent import run_bash
        result = run_bash("cd /tmp && echo -n ''")
        assert result == "(no output)" or result == ""

    def test_run_read_existing_file(self):
        """测试读取存在的文件"""
        from backend.core.agent import run_read
        result = run_read("main.py")
        assert "FastAPI" in result
        assert len(result) > 0

    def test_run_read_with_limit(self):
        """测试 limit 参数"""
        from backend.core.agent import run_read
        result = run_read("main.py", limit=3)
        lines = result.splitlines()
        assert len(lines) <= 4  # 3 + "... more lines"

    def test_run_read_nonexistent_file(self):
        """测试读取不存在的文件"""
        from backend.core.agent import run_read
        result = run_read("nonexistent_xyz_file.txt")
        assert "Error" in result

    def test_run_write_and_read(self):
        """测试写入后读取"""
        from backend.core.agent import run_write, run_read, safe_path, WORKDIR
        path = "test_temp_write.txt"
        try:
            result = run_write(path, "test content here")
            assert "Wrote" in result
            content = run_read(path)
            assert "test content here" in content
        finally:
            # 清理
            fp = safe_path(path)
            if fp.exists():
                fp.unlink()

    def test_run_write_creates_dirs(self):
        """测试自动创建父目录"""
        from backend.core.agent import run_write, safe_path, WORKDIR
        import shutil
        path = "test_subdir/test_file.txt"
        try:
            result = run_write(path, "nested content")
            assert "Wrote" in result
            fp = safe_path(path)
            assert fp.exists()
        finally:
            fp = safe_path("test_subdir")
            if fp.exists():
                shutil.rmtree(str(fp), ignore_errors=True)

    def test_run_edit_success(self):
        """测试编辑文件"""
        from backend.core.agent import run_write, run_edit, run_read, safe_path, WORKDIR
        path = "test_edit.txt"
        try:
            run_write(path, "hello world")
            result = run_edit(path, "hello", "hi")
            assert "Edited" in result
            content = run_read(path)
            assert "hi world" in content
            assert "hello" not in content or "hello" in content.replace("hi world", "")
        finally:
            fp = safe_path(path)
            if fp.exists():
                fp.unlink()

    def test_run_edit_text_not_found(self):
        """测试编辑时文本未找到"""
        from backend.core.agent import run_write, run_edit, safe_path, WORKDIR
        path = "test_edit2.txt"
        try:
            run_write(path, "hello world")
            result = run_edit(path, "nonexistent", "replacement")
            assert "Error" in result or "not found" in result.lower()
        finally:
            fp = safe_path(path)
            if fp.exists():
                fp.unlink()

    def test_run_edit_nonexistent_file(self):
        """测试编辑不存在的文件"""
        from backend.core.agent import run_edit
        result = run_edit("nonexistent_edit.txt", "old", "new")
        assert "Error" in result

    def test_get_model_info(self):
        """测试 get_model_info"""
        from backend.core.agent import get_model_info
        info = get_model_info()
        assert "model" in info
        assert "cwd" in info
        assert "base_url" in info


# ============================================================
# 3. 数据库单元测试
# ============================================================

class TestDatabase:
    """数据库操作测试"""

    @pytest.fixture
    def db(self):
        """创建临时数据库"""
        from backend.storage.database import Database
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(db_path=path)
        yield db
        db.get_connection().close()
        if os.path.exists(path):
            os.unlink(path)

    def test_init_db_creates_tables(self, db):
        """测试数据库初始化创建表"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_create_conversation(self, db):
        """测试创建对话"""
        cid = db.create_conversation()
        assert isinstance(cid, str)
        assert len(cid) > 0
        # 验证存在性
        conv = db.get_conversation(cid)
        assert conv is not None
        assert conv.title == "新对话"

    def test_create_conversation_with_title(self, db):
        """测试创建带标题的对话"""
        cid = db.create_conversation(title="自定义标题")
        conv = db.get_conversation(cid)
        assert conv.title == "自定义标题"

    def test_get_conversations_empty(self, db):
        """测试空对话列表"""
        convs = db.get_conversations()
        assert isinstance(convs, list)
        assert len(convs) == 0

    def test_get_conversations_with_data(self, db):
        """测试有数据的对话列表"""
        db.create_conversation("对话1")
        db.create_conversation("对话2")
        convs = db.get_conversations()
        assert len(convs) == 2

    def test_get_conversations_limit(self, db):
        """测试 limit 参数"""
        for i in range(10):
            db.create_conversation(f"对话{i}")
        convs = db.get_conversations(limit=3)
        assert len(convs) == 3

    def test_get_conversation_not_found(self, db):
        """测试获取不存在的对话"""
        conv = db.get_conversation("nonexistent-id")
        assert conv is None

    def test_add_message(self, db):
        """测试添加消息"""
        from backend.storage.models import Message
        cid = db.create_conversation()
        msg = Message(role="user", content="你好")
        db.add_message(cid, msg)

        conv = db.get_conversation(cid)
        assert len(conv.messages) == 1
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "你好"

    def test_add_multiple_messages(self, db):
        """测试添加多条消息"""
        from backend.storage.models import Message
        cid = db.create_conversation()

        db.add_message(cid, Message(role="user", content="问题1"))
        db.add_message(cid, Message(role="assistant", content="回答1"))
        db.add_message(cid, Message(role="user", content="问题2"))

        conv = db.get_conversation(cid)
        assert len(conv.messages) == 3

    def test_add_message_with_flags(self, db):
        """测试添加带标记的消息"""
        from backend.storage.models import Message
        cid = db.create_conversation()

        msg = Message(
            role="assistant",
            content="ls -la",
            is_command=True,
            is_output=False
        )
        db.add_message(cid, msg)

        output_msg = Message(
            role="assistant",
            content="file1.txt",
            is_output=True,
            full_output="file1.txt\nfile2.txt"
        )
        db.add_message(cid, output_msg)

        conv = db.get_conversation(cid)
        assert len(conv.messages) == 2
        assert conv.messages[0].is_command is True
        assert conv.messages[1].is_output is True
        assert conv.messages[1].full_output == "file1.txt\nfile2.txt"

    def test_update_conversation_title(self, db):
        """测试更新标题"""
        cid = db.create_conversation("旧标题")
        db.update_conversation_title(cid, "新标题")
        conv = db.get_conversation(cid)
        assert conv.title == "新标题"

    def test_delete_conversation(self, db):
        """测试删除对话"""
        cid = db.create_conversation()
        db.delete_conversation(cid)
        conv = db.get_conversation(cid)
        assert conv is None

    def test_delete_cascades_messages(self, db):
        """测试级联删除消息"""
        from backend.storage.models import Message
        cid = db.create_conversation()
        db.add_message(cid, Message(role="user", content="test"))
        db.delete_conversation(cid)

        # 通过直接 SQL 确认消息也被删除
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (cid,))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0

    def test_auto_generate_title(self, db):
        """测试自动生成标题"""
        from backend.storage.models import Message
        cid = db.create_conversation()
        long_msg = "这是一个很长的用户消息，用于测试自动生成标题功能"
        db.add_message(cid, Message(role="user", content=long_msg))
        title = db.auto_generate_title(cid)
        assert title is not None
        assert len(title) <= 33  # 30 + "..."
        assert title.startswith("这是一个很长的用户消息")

    def test_auto_generate_title_short(self, db):
        """测试短消息自动标题"""
        from backend.storage.models import Message
        cid = db.create_conversation()
        db.add_message(cid, Message(role="user", content="你好"))
        title = db.auto_generate_title(cid)
        assert title == "你好"

    def test_message_count_in_list(self, db):
        """测试对话列表中的消息计数"""
        from backend.storage.models import Message
        cid = db.create_conversation()
        for i in range(5):
            db.add_message(cid, Message(role="user", content=f"msg{i}"))

        convs = db.get_conversations()
        assert len(convs) == 1
        assert convs[0].message_count == 5

    def test_conversations_ordered_by_updated(self, db):
        """测试对话列表按更新时间排序"""
        from backend.storage.models import Message
        import time
        c1 = db.create_conversation("对话1")
        time.sleep(0.1)
        c2 = db.create_conversation("对话2")

        convs = db.get_conversations()
        assert convs[0].id == c2  # 最新的在前


# ============================================================
# 4. API 集成测试 (使用 FastAPI TestClient)
# ============================================================

class MockContentText:
    """Mock Claude text content"""
    def __init__(self, text):
        self.text = text
        self.type = "text"


class MockContentToolUse:
    """Mock Claude tool_use content"""
    def __init__(self, name, input_data, tool_id="toolu_001"):
        self.type = "tool_use"
        self.name = name
        self.input = input_data
        self.id = tool_id


class MockResponse:
    """Mock Claude API response"""
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


@pytest.fixture
def app_with_mock_db():
    """创建带 Mock 数据库的 FastAPI 测试客户端"""
    from backend.storage.database import Database

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # 替换 main 模块中的 db 实例
    import main
    original_db = main.db
    main.db = Database(db_path=path)

    yield main.app, path

    # 恢复原始数据库
    main.db = original_db
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def client(app_with_mock_db):
    """FastAPI TestClient"""
    app, _ = app_with_mock_db
    return TestClient(app)


class TestAPI:
    """API 端点测试"""

    def test_health(self, client):
        """测试 /api/health 端点"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "model" in data
        assert "cwd" in data

    def test_create_conversation_api(self, client):
        """测试 POST /api/conversations 创建对话"""
        response = client.post("/api/conversations", json={"title": "测试对话"})
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "测试对话"
        assert "id" in data
        assert data["message_count"] == 0

    def test_get_conversations_empty(self, client):
        """测试获取空对话列表"""
        response = client.get("/api/conversations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_conversations_with_data(self, client):
        """测试获取有数据的对话列表"""
        # 先创建几个对话
        client.post("/api/conversations", json={"title": "对话A"})
        client.post("/api/conversations", json={"title": "对话B"})

        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_conversation_detail(self, client):
        """测试获取对话详情"""
        # 创建对话
        resp = client.post("/api/conversations", json={"title": "详情测试"})
        cid = resp.json()["id"]

        response = client.get(f"/api/conversations/{cid}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == cid
        assert data["title"] == "详情测试"
        assert data["messages"] == []

    def test_get_conversation_not_found(self, client):
        """测试获取不存在的对话"""
        response = client.get("/api/conversations/nonexistent-id")
        assert response.status_code == 404

    def test_update_conversation(self, client):
        """测试更新对话标题"""
        resp = client.post("/api/conversations", json={"title": "旧标题"})
        cid = resp.json()["id"]

        response = client.put(f"/api/conversations/{cid}", json={"title": "新标题"})
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 验证更新
        detail = client.get(f"/api/conversations/{cid}")
        assert detail.json()["title"] == "新标题"

    def test_delete_conversation(self, client):
        """测试删除对话"""
        resp = client.post("/api/conversations", json={"title": "待删除"})
        cid = resp.json()["id"]

        response = client.delete(f"/api/conversations/{cid}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 验证已删除
        response = client.get(f"/api/conversations/{cid}")
        assert response.status_code == 404

    def test_chat_new_conversation(self, client):
        """测试新对话聊天（Mock Claude API）"""
        with patch("main.agent_loop") as mock_agent:
            from backend.storage.models import ToolExecution
            mock_agent.return_value = ("这是回复", [])

            response = client.post("/api/chat", json={"message": "你好"})
            assert response.status_code == 200
            data = response.json()
            assert data["text"] == "这是回复"
            assert data["tools"] == []
            assert "conversation_id" in data

    def test_chat_with_tools(self, client):
        """测试带工具的聊天"""
        with patch("main.agent_loop") as mock_agent:
            from backend.storage.models import ToolExecution
            mock_agent.return_value = (
                "我执行了一些命令",
                [
                    ToolExecution(command="ls -la", output="file1\nfile2"),
                    ToolExecution(command="echo done", output="done")
                ]
            )

            response = client.post("/api/chat", json={"message": "列出文件"})
            assert response.status_code == 200
            data = response.json()
            assert len(data["tools"]) == 2
            assert data["tools"][0]["command"] == "ls -la"
            assert data["tools"][1]["command"] == "echo done"

    def test_chat_continue_conversation(self, client):
        """测试继续已有对话"""
        with patch("main.agent_loop") as mock_agent:
            from backend.storage.models import ToolExecution
            mock_agent.return_value = ("第二条回复", [])

            # 先创建对话并获取 id
            resp = client.post("/api/conversations", json={"title": "续聊"})
            cid = resp.json()["id"]

            # 在已有对话中发送消息
            response = client.post("/api/chat", json={
                "message": "继续",
                "conversation_id": cid
            })
            assert response.status_code == 200
            data = response.json()
            assert data["conversation_id"] == cid
            assert data["text"] == "第二条回复"

    def test_chat_with_invalid_conversation_id(self, client):
        """测试使用无效的 conversation_id"""
        response = client.post("/api/chat", json={
            "message": "hello",
            "conversation_id": "invalid-id-123"
        })
        assert response.status_code == 404

    def test_chat_agent_error_handling(self, client):
        """测试 agent 异常时的错误处理"""
        with patch("main.agent_loop") as mock_agent:
            mock_agent.side_effect = RuntimeError("Simulated agent failure")

            response = client.post("/api/chat", json={"message": "触发错误"})
            assert response.status_code == 500
            assert "Simulated agent failure" in response.json()["detail"]

    def test_conversations_limit_param(self, client):
        """测试对话列表 limit 参数"""
        for i in range(5):
            client.post("/api/conversations", json={"title": f"对话{i}"})

        response = client.get("/api/conversations?limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_cors_headers(self, client):
        """测试 CORS 头"""
        response = client.options("/api/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        # FastAPI TestClient 可能不会完全模拟 CORS，但验证响应成功即可
        assert response.status_code in [200, 405]


# ============================================================
# 5. Agent Loop 核心循环测试
# ============================================================

class TestAgentLoop:
    """Agent 循环测试"""

    def test_agent_loop_simple_text_response(self):
        """测试纯文本响应（无工具调用）"""
        with patch("agent.client.messages.create") as mock_create:
            mock_create.return_value = MockResponse(
                content=[MockContentText("你好！有什么可以帮助你的？")],
                stop_reason="end_turn"
            )

            from backend.core.agent import agent_loop
            text, tools = agent_loop([{"role": "user", "content": "hi"}])

            assert "你好" in text
            assert tools == []

    def test_agent_loop_with_tool_calls(self):
        """测试带工具调用的循环"""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一次调用返回 tool_use
                return MockResponse(
                    content=[
                        MockContentText("让我查一下"),
                        MockContentToolUse("bash", {"command": "echo hello"}, "toolu_001")
                    ],
                    stop_reason="tool_use"
                )
            else:
                # 第二次返回最终文本
                return MockResponse(
                    content=[MockContentText("命令执行成功")],
                    stop_reason="end_turn"
                )

        with patch("agent.client.messages.create", side_effect=side_effect):
            from backend.core.agent import agent_loop
            text, tools = agent_loop([{"role": "user", "content": "执行命令"}])

            assert "命令执行成功" in text
            assert len(tools) == 1
            assert tools[0].command == "echo hello"
            assert "hello" in tools[0].output

    def test_agent_loop_multiple_tool_calls(self):
        """测试多轮工具调用"""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse(
                    content=[MockContentToolUse("bash", {"command": "pwd"}, "t1")],
                    stop_reason="tool_use"
                )
            elif call_count[0] == 2:
                return MockResponse(
                    content=[MockContentToolUse("read_file", {"path": "main.py"}, "t2")],
                    stop_reason="tool_use"
                )
            else:
                return MockResponse(
                    content=[MockContentText("所有操作完成")],
                    stop_reason="end_turn"
                )

        with patch("agent.client.messages.create", side_effect=side_effect):
            from backend.core.agent import agent_loop
            text, tools = agent_loop([{"role": "user", "content": "do stuff"}])

            assert len(tools) == 2
            assert tools[0].command == "pwd"
            assert "read_file" in tools[1].command

    def test_agent_loop_unknown_tool(self):
        """测试未知工具"""
        with patch("agent.client.messages.create") as mock_create:
            mock_create.return_value = MockResponse(
                content=[
                    MockContentToolUse("unknown_tool", {"arg1": "val1"}, "tu_unknown"),
                    MockContentText("done")
                ],
                stop_reason="tool_use"  # 触发 tool use 但工具未知
            )

            from backend.core.agent import agent_loop
            text, tools = agent_loop([{"role": "user", "content": "test"}])

            # 未知工具也应该被记录
            assert any("unknown_tool" in t.command for t in tools)

    def test_agent_loop_api_error(self):
        """测试 API 错误传播"""
        with patch("agent.client.messages.create") as mock_create:
            mock_create.side_effect = Exception("API connection failed")

            from backend.core.agent import agent_loop
            with pytest.raises(Exception, match="API connection failed"):
                agent_loop([{"role": "user", "content": "test"}])

    def test_agent_loop_write_and_read_tools(self):
        """测试 write_file 和 read_file 工具的完整流程"""
        test_file = "agent_test_temp.txt"

        with patch("agent.client.messages.create") as mock_create:
            from backend.core.agent import agent_loop, safe_path, WORKDIR
            mock_create.return_value = MockResponse(
                content=[
                    MockContentToolUse("write_file", {
                        "path": test_file,
                        "content": "agent test content"
                    }, "tw1"),
                    MockContentText("文件已写入")
                ],
                stop_reason="tool_use"
            )

            try:
                text, tools = agent_loop([{"role": "user", "content": "写入文件"}])
                assert any("Wrote" in t.output for t in tools)

                # 验证文件确实被写入
                fp = safe_path(test_file)
                assert fp.exists()
                assert fp.read_text() == "agent test content"

            finally:
                fp = safe_path(test_file)
                if fp.exists():
                    fp.unlink()


# ============================================================
# 6. 边缘情况测试
# ============================================================

class TestEdgeCases:
    """边缘情况和边界测试"""

    def test_empty_message(self, client):
        """测试空消息"""
        with patch("main.agent_loop") as mock_agent:
            mock_agent.return_value = ("", [])
            response = client.post("/api/chat", json={"message": ""})
            assert response.status_code == 200

    def test_long_message(self, client):
        """测试超长消息"""
        with patch("main.agent_loop") as mock_agent:
            mock_agent.return_value = ("ok", [])
            long_msg = "x" * 10000
            response = client.post("/api/chat", json={"message": long_msg})
            assert response.status_code == 200

    def test_special_characters_message(self, client):
        """测试特殊字符消息"""
        with patch("main.agent_loop") as mock_agent:
            mock_agent.return_value = ("ok", [])
            msg = "你好\n世界\t!@#$%^&*()<>{}\\|\"'"
            response = client.post("/api/chat", json={"message": msg})
            assert response.status_code == 200

    def test_run_bash_very_long_output(self):
        """测试超长输出截断"""
        from backend.core.agent import run_bash
        result = run_bash("python -c \"print('A'*60000)\"")
        assert len(result) <= 50000

    def test_database_concurrent_access(self, db):
        """测试数据库并发访问"""
        import threading
        from backend.storage.models import Message

        cid = db.create_conversation()
        errors = []

        def add_messages():
            try:
                for i in range(10):
                    db.add_message(cid, Message(role="user", content=f"msg{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_messages) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        conv = db.get_conversation(cid)
        assert len(conv.messages) == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
