"""
任务管理模块

封装持久化任务的编排逻辑，并在 Database 的基础能力之上补充
多 Agent 协作所需的任务认领与任务扫描功能。

职责：
1. 对接持久化任务存储（通过 Database）
2. 提供任务创建、查询、更新、删除等统一接口
3. 提供任务编排相关能力：
   - claim：认领任务
   - scan_unclaimed_tasks：扫描可认领任务

说明：
- 该模块属于 Agent 编排层，而不是底层存储实现
- Database 负责存储细节，TaskManager 负责任务规则与编排语义
- 因此放在 core/
"""

import json
from typing import List
from datetime import datetime


class TaskManager:
    """任务管理器 - 封装 Database 并添加多 agent 编排功能"""
    
    def __init__(self, db):
        self.db = db
    
    def create(self, conversation_id: str, subject: str, description: str = "", 
               project: str = "", tags: list = None) -> dict:
        """创建任务（委托给 database）"""
        return self.db.create_task(conversation_id, subject, description, project, tags or [])
    
    def get(self, task_id: int) -> dict:
        """获取任务详情（委托给 database）"""
        return self.db.get_task(task_id)
    
    def update(self, task_id: int, status: str = None, 
               add_blocked_by: list = None, remove_blocked_by: list = None) -> dict:
        """更新任务状态或依赖（委托给 database）"""
        return self.db.update_task(task_id, status, add_blocked_by, remove_blocked_by)
    
    def list_tasks(self, conversation_id: str, project_filter: str = None) -> str:
        """列出对话的所有任务（委托给 database）"""
        return self.db.list_tasks(conversation_id, project_filter)
    
    def list_all_tasks(self, status_filter: str = None, project_filter: str = None) -> str:
        """列出所有任务（委托给 database）"""
        return self.db.list_all_tasks(status_filter, project_filter)
    
    def delete(self, task_id: int) -> dict:
        """删除任务（委托给 database）"""
        return self.db.delete_task(task_id)
    
    def claim(self, task_id: int, owner: str) -> str:
        """认领任务并将其置为 in_progress。"""
        task = self.get(task_id)
        if not task:
            return f"Error: Task {task_id} not found"
        
        if task.get('owner') and task['owner'] != owner:
            return f"Error: Task {task_id} already claimed by {task['owner']}"
        
        if task.get('status') not in ('pending', 'in_progress'):
            return f"Error: Task {task_id} cannot be claimed (status: {task['status']})"
        
        if task.get('blocked_by') and json.loads(task['blocked_by']):
            return f"Error: Task {task_id} is blocked by {task['blocked_by']}"
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tasks
            SET owner = ?, status = 'in_progress', updated_at = ?
            WHERE id = ?
        """, (owner, datetime.now(), task_id))
        conn.commit()
        conn.close()
        
        return f"Claimed task #{task_id} for {owner}"
    
    def scan_unclaimed_tasks(self, conversation_id: str = None) -> List[dict]:
        """扫描所有可被认领的待办任务。"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if conversation_id:
            cursor.execute("""
                SELECT id, conversation_id, subject, description, project, tags, status, blocked_by, owner
                FROM tasks
                WHERE conversation_id = ? 
                  AND status = 'pending' 
                  AND (owner IS NULL OR owner = '')
                  AND (blocked_by IS NULL OR blocked_by = '[]')
                ORDER BY id ASC
            """, (conversation_id,))
        else:
            cursor.execute("""
                SELECT id, conversation_id, subject, description, project, tags, status, blocked_by, owner
                FROM tasks
                WHERE status = 'pending' 
                  AND (owner IS NULL OR owner = '')
                  AND (blocked_by IS NULL OR blocked_by = '[]')
                ORDER BY id ASC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            tasks.append({
                "id": row['id'],
                "conversation_id": row['conversation_id'],
                "subject": row['subject'],
                "description": row['description'],
                "project": row['project'],
                "tags": json.loads(row['tags']),
                "status": row['status'],
                "blocked_by": json.loads(row['blocked_by']),
                "owner": row['owner']
            })
        
        return tasks
