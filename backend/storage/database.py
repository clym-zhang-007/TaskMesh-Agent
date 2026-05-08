"""
数据库操作模块

使用 SQLite 管理对话、消息和任务数据。
提供完整的 CRUD 操作和数据持久化功能。

数据库结构：
1. conversations 表 - 存储对话基本信息
2. messages 表 - 存储消息历史
3. tasks 表 - 存储持久化任务（关联到对话）

特性：
- 自动创建数据库和表结构
- 支持事务操作
- 自动时间戳管理
- 外键约束和级联删除
- 任务依赖关系管理

"""

import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path
import uuid

from backend.schema.models import Conversation, ConversationDetail, Message


class Database:
    """
    数据库管理类
    
    封装所有数据库操作，提供对话和消息的 CRUD 功能。
    使用 SQLite 作为存储引擎，支持自动初始化和连接管理。
    
    Attributes:
        db_path (str): 数据库文件路径
    
    Example:
        >>> db = Database("conversations.db")
        >>> conversation_id = db.create_conversation("新对话")
        >>> db.add_message(conversation_id, Message(...))
    """
    
    def __init__(self, db_path: str = "conversations.db"):
        """
        初始化数据库
        
        Args:
            db_path (str): 数据库文件路径，默认为 "conversations.db"
        """
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """
        获取数据库连接
        
        创建并配置 SQLite 连接，设置 row_factory 以支持字典式访问。
        
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """
        初始化数据库表结构
        
        创建 conversations、messages 和 tasks 表（如果不存在）。
        设置外键约束和索引以优化查询性能。
        
        表结构：
        - conversations: 对话基本信息
        - messages: 消息历史记录
        - tasks: 持久化任务（关联到对话）
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 创建对话表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建消息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                is_tool_call BOOLEAN DEFAULT FALSE,
                is_tool_output BOOLEAN DEFAULT FALSE,
                is_error BOOLEAN DEFAULT FALSE,
                tool_name TEXT,
                full_output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        # 创建任务表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                subject TEXT NOT NULL,
                description TEXT DEFAULT '',
                project TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                blocked_by TEXT DEFAULT '[]',
                owner TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation 
            ON messages(conversation_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_conversation 
            ON tasks(conversation_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status 
            ON tasks(status)
        """)
        
        conn.commit()
        conn.close()
    
    def create_conversation(self, title: str = "新对话") -> str:
        """
        创建新对话
        
        生成唯一的对话 ID，并在数据库中创建新记录。
        
        Args:
            title (str): 对话标题，默认为 "新对话"
        
        Returns:
            str: 新创建的对话 ID（UUID 格式）
        
        Example:
            >>> conversation_id = db.create_conversation("Python 学习")
            >>> print(conversation_id)
            "550e8400-e29b-41d4-a716-446655440000"
        """
        conversation_id = str(uuid.uuid4())
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, title, datetime.now(), datetime.now()))
        
        conn.commit()
        conn.close()
        
        return conversation_id
    
    def get_conversations(self, limit: int = 50) -> List[Conversation]:
        """
        获取对话列表
        
        按更新时间倒序返回对话列表，包含每个对话的消息数量。
        
        Args:
            limit (int): 返回的最大对话数量，默认 50
        
        Returns:
            List[Conversation]: 对话列表，按 updated_at 降序排列
        
        Example:
            >>> conversations = db.get_conversations(limit=10)
            >>> for conv in conversations:
            ...     print(f"{conv.title}: {conv.message_count} 条消息")
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                c.id, 
                c.title, 
                c.created_at, 
                c.updated_at,
                COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        conversations = []
        for row in rows:
            conversations.append(Conversation(
                id=row['id'],
                title=row['title'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                message_count=row['message_count']
            ))
        
        return conversations
    
    def get_conversation(self, conversation_id: str) -> Optional[ConversationDetail]:
        """
        获取对话详情
        
        返回指定对话的完整信息，包括所有消息历史。
        
        Args:
            conversation_id (str): 对话 ID
        
        Returns:
            Optional[ConversationDetail]: 对话详情对象，如果不存在则返回 None
        
        Example:
            >>> detail = db.get_conversation("550e8400-...")
            >>> if detail:
            ...     print(f"标题: {detail.title}")
            ...     print(f"消息数: {len(detail.messages)}")
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取对话信息
        cursor.execute("""
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
        """, (conversation_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        # 获取消息列表
        cursor.execute("""
            SELECT role, content, is_tool_call, is_tool_output, is_error, tool_name, full_output, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """, (conversation_id,))
        
        message_rows = cursor.fetchall()
        conn.close()
        
        messages = []
        for msg_row in message_rows:
            messages.append(Message(
                role=msg_row['role'],
                content=msg_row['content'],
                is_tool_call=bool(msg_row['is_tool_call']),
                is_tool_output=bool(msg_row['is_tool_output']),
                is_error=bool(msg_row['is_error']),
                tool_name=msg_row['tool_name'],
                full_output=msg_row['full_output'],
                created_at=datetime.fromisoformat(msg_row['created_at']) if msg_row['created_at'] else None
            ))
        
        return ConversationDetail(
            id=row['id'],
            title=row['title'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            messages=messages
        )
    
    def add_message(self, conversation_id: str, message: Message):
        """
        添加消息到对话
        
        将新消息插入数据库，并自动更新对话的 updated_at 时间戳。
        
        Args:
            conversation_id (str): 对话 ID
            message (Message): 消息对象
        
        Example:
            >>> msg = Message(role="user", content="你好")
            >>> db.add_message(conversation_id, msg)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO messages 
            (conversation_id, role, content, is_tool_call, is_tool_output, is_error, tool_name, full_output, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conversation_id,
            message.role,
            message.content,
            message.is_tool_call,
            message.is_tool_output,
            message.is_error,
            message.tool_name,
            message.full_output,
            message.created_at or datetime.now()
        ))
        
        # 更新对话的 updated_at
        cursor.execute("""
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
        """, (datetime.now(), conversation_id))
        
        conn.commit()
        conn.close()
    
    def update_conversation_title(self, conversation_id: str, title: str):
        """
        更新对话标题
        
        修改指定对话的标题，并更新 updated_at 时间戳。
        
        Args:
            conversation_id (str): 对话 ID
            title (str): 新标题
        
        Example:
            >>> db.update_conversation_title(conversation_id, "Python 进阶学习")
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ?
        """, (title, datetime.now(), conversation_id))
        
        conn.commit()
        conn.close()
    
    def delete_conversation(self, conversation_id: str):
        """
        删除对话
        
        删除指定对话及其所有消息（级联删除）。
        
        Args:
            conversation_id (str): 对话 ID
        
        Example:
            >>> db.delete_conversation(conversation_id)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先删除消息
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        # 再删除对话
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        
        conn.commit()
        conn.close()
    
    def auto_generate_title(self, conversation_id: str):
        """
        自动生成对话标题
        
        基于对话中第一条用户消息的内容自动生成标题。
        取前 30 个字符，超出部分用 "..." 表示。
        
        Args:
            conversation_id (str): 对话 ID
        
        Returns:
            Optional[str]: 生成的标题，如果没有用户消息则返回 None
        
        Example:
            >>> title = db.auto_generate_title(conversation_id)
            >>> print(title)
            "列出当前目录的文件并创建一个测试文..."
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT content
            FROM messages
            WHERE conversation_id = ? AND role = 'user'
            ORDER BY created_at ASC
            LIMIT 1
        """, (conversation_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # 取前30个字符作为标题
            content = row['content']
            title = content[:30] + ('...' if len(content) > 30 else '')
            self.update_conversation_title(conversation_id, title)
            return title
        
        return None
    
    # ==================== 任务管理方法 ====================
    
    def create_task(self, conversation_id: str, subject: str, description: str = "", project: str = "", tags: list = None) -> dict:
        """
        创建持久化任务
        
        在指定对话中创建新任务，任务会持久化到数据库。
        
        Args:
            conversation_id (str): 对话 ID
            subject (str): 任务标题
            description (str): 任务描述，默认为空
            project (str): 项目名称，用于分组任务，默认为空
            tags (list): 标签列表，用于分类任务，默认为空列表
        
        Returns:
            dict: 创建的任务对象
        
        Example:
            >>> task = db.create_task(conversation_id, "实现用户认证", "添加 JWT 认证功能", project="博客系统", tags=["backend", "auth"])
            >>> print(task['id'])
            1
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        
        cursor.execute("""
            INSERT INTO tasks (conversation_id, subject, description, project, tags, status, blocked_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', '[]', ?, ?)
        """, (conversation_id, subject, description, project, tags_json, datetime.now(), datetime.now()))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return self.get_task(task_id)
    
    def get_task(self, task_id: int) -> Optional[dict]:
        """
        获取任务详情
        
        Args:
            task_id (int): 任务 ID
        
        Returns:
            Optional[dict]: 任务对象，如果不存在则返回 None
        
        Example:
            >>> task = db.get_task(1)
            >>> print(task['subject'])
            "实现用户认证"
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, conversation_id, subject, description, project, tags, status, blocked_by, owner, 
                   created_at, updated_at, completed_at
            FROM tasks
            WHERE id = ?
        """, (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "id": row['id'],
            "conversation_id": row['conversation_id'],
            "subject": row['subject'],
            "description": row['description'],
            "project": row['project'],
            "tags": json.loads(row['tags']),
            "status": row['status'],
            "blocked_by": json.loads(row['blocked_by']),
            "owner": row['owner'],
            "created_at": row['created_at'],
            "updated_at": row['updated_at'],
            "completed_at": row['completed_at']
        }
    
    def update_task(self, task_id: int, status: str = None, 
                   add_blocked_by: list = None, remove_blocked_by: list = None) -> dict:
        """
        更新任务状态或依赖关系
        
        Args:
            task_id (int): 任务 ID
            status (str): 新状态（pending/in_progress/completed/deleted）
            add_blocked_by (list): 添加依赖的任务 ID 列表
            remove_blocked_by (list): 移除依赖的任务 ID 列表
        
        Returns:
            dict: 更新后的任务对象
        
        Example:
            >>> task = db.update_task(2, status="in_progress")
            >>> task = db.update_task(3, add_blocked_by=[1, 2])
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取当前任务
        task = self.get_task(task_id)
        if not task:
            conn.close()
            raise ValueError(f"Task {task_id} not found")
        
        blocked_by = task['blocked_by']
        
        # 更新状态
        if status:
            if status not in ("pending", "in_progress", "completed", "deleted"):
                raise ValueError(f"Invalid status: {status}")
            
            completed_at = datetime.now() if status == "completed" else None
            
            cursor.execute("""
                UPDATE tasks
                SET status = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
            """, (status, datetime.now(), completed_at, task_id))
            
            # 如果任务完成，清除其他任务对它的依赖
            if status == "completed":
                self._clear_task_dependency(task_id, cursor)
        
        # 更新依赖关系
        if add_blocked_by:
            blocked_by = list(set(blocked_by + add_blocked_by))
        
        if remove_blocked_by:
            blocked_by = [x for x in blocked_by if x not in remove_blocked_by]
        
        if add_blocked_by or remove_blocked_by:
            cursor.execute("""
                UPDATE tasks
                SET blocked_by = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(blocked_by), datetime.now(), task_id))
        
        conn.commit()
        conn.close()
        
        return self.get_task(task_id)
    
    def _clear_task_dependency(self, completed_task_id: int, cursor):
        """
        清除其他任务对已完成任务的依赖
        
        当任务完成时，自动从所有其他任务的 blocked_by 中移除该任务 ID。
        
        Args:
            completed_task_id (int): 已完成的任务 ID
            cursor: 数据库游标
        """
        # 获取所有任务
        cursor.execute("SELECT id, blocked_by FROM tasks")
        rows = cursor.fetchall()
        
        for row in rows:
            blocked_by = json.loads(row['blocked_by'])
            if completed_task_id in blocked_by:
                blocked_by.remove(completed_task_id)
                cursor.execute("""
                    UPDATE tasks
                    SET blocked_by = ?, updated_at = ?
                    WHERE id = ?
                """, (json.dumps(blocked_by), datetime.now(), row['id']))
    
    def list_tasks(self, conversation_id: str, project_filter: str = None) -> str:
        """
        列出对话的所有任务
        
        返回格式化的任务列表字符串，显示状态和依赖关系。
        
        Args:
            conversation_id (str): 对话 ID
            project_filter (str): 可选的项目过滤
        
        Returns:
            str: 格式化的任务列表
        
        Example:
            >>> tasks_str = db.list_tasks(conversation_id)
            >>> print(tasks_str)
            [x] #1: 设计数据库 [博客系统]
            [>] #2: 实现用户模型 [博客系统]
            [ ] #3: 实现认证 API [博客系统] (blocked by: [2])
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if project_filter:
            cursor.execute("""
                SELECT id, subject, project, status, blocked_by
                FROM tasks
                WHERE conversation_id = ? AND project = ? AND status != 'deleted'
                ORDER BY id ASC
            """, (conversation_id, project_filter))
        else:
            cursor.execute("""
                SELECT id, subject, project, status, blocked_by
                FROM tasks
                WHERE conversation_id = ? AND status != 'deleted'
                ORDER BY id ASC
            """, (conversation_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "No tasks in this conversation."
        
        lines = []
        for row in rows:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]"
            }.get(row['status'], "[?]")
            
            blocked_by = json.loads(row['blocked_by'])
            blocked_str = f" (blocked by: {blocked_by})" if blocked_by else ""
            
            project_str = f" [{row['project']}]" if row['project'] else ""
            
            lines.append(f"{marker} #{row['id']}: {row['subject']}{project_str}{blocked_str}")
        
        return "\n".join(lines)
    
    def delete_task(self, task_id: int) -> dict:
        """
        删除任务（软删除）
        
        将任务状态设置为 'deleted'，不从数据库中物理删除。
        
        Args:
            task_id (int): 任务 ID
        
        Returns:
            dict: 更新后的任务对象
        
        Example:
            >>> task = db.delete_task(3)
            >>> print(task['status'])
            "deleted"
        """
        return self.update_task(task_id, status="deleted")
    
    def list_all_tasks(self, status_filter: str = None, project_filter: str = None, include_completed: bool = False) -> str:
        """
        列出所有任务（跨对话）
        
        返回格式化的任务列表字符串，显示状态、依赖关系和所属项目。
        默认不显示已完成的任务。
        
        Args:
            status_filter (str): 可选的状态过滤（pending/in_progress/completed）
            project_filter (str): 可选的项目过滤
            include_completed (bool): 是否包含已完成的任务，默认 False
        
        Returns:
            str: 格式化的任务列表
        
        Example:
            >>> tasks_str = db.list_all_tasks(project_filter="博客系统")
            >>> print(tasks_str)
            === 博客系统 ===
            [>] #2: 实现用户模型
            [ ] #3: 实现认证 API (blocked by: [2])
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT id, conversation_id, subject, project, status, blocked_by
            FROM tasks
            WHERE status != 'deleted'
        """
        params = []
        
        # 默认不显示已完成的任务
        if not include_completed and status_filter != 'completed':
            query += " AND status != 'completed'"
        
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
        
        if project_filter:
            query += " AND project = ?"
            params.append(project_filter)
        
        query += " ORDER BY project, id ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "No active tasks found."
        
        lines = []
        current_project = None
        
        for row in rows:
            # 项目分组显示
            if row['project'] and row['project'] != current_project:
                current_project = row['project']
                lines.append(f"\n=== {current_project} ===")
            elif not row['project'] and current_project is not None:
                current_project = None
                lines.append(f"\n=== 未分类 ===")
            
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]"
            }.get(row['status'], "[?]")
            
            blocked_by = json.loads(row['blocked_by'])
            blocked_str = f" (blocked by: {blocked_by})" if blocked_by else ""
            
            lines.append(f"{marker} #{row['id']}: {row['subject']}{blocked_str}")
        
        return "\n".join(lines)
