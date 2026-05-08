"""
对话管理路由模块

提供对话的 CRUD 操作接口。
使用 FastAPI 的 APIRouter 实现模块化路由。

端点列表：
- GET    /api/conversations          - 获取对话列表
- POST   /api/conversations          - 创建新对话
- GET    /api/conversations/{id}     - 获取对话详情
- PUT    /api/conversations/{id}     - 更新对话标题
- DELETE /api/conversations/{id}     - 删除对话

依赖注入：
- 使用 init_db() 函数注入数据库实例
- 避免循环导入问题

"""

from typing import List
from fastapi import APIRouter, HTTPException

from backend.schema.models import (
    Conversation, ConversationDetail,
    ConversationCreate, ConversationUpdate
)
from backend.storage.database import Database

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# 数据库实例（将在 main.py 中注入）
db: Database = None


def init_db(database: Database):
    """
    初始化数据库实例
    
    由 main.py 调用，注入数据库实例到路由模块。
    
    Args:
        database (Database): 数据库实例
    """
    global db
    db = database


@router.get("", response_model=List[Conversation])
def get_conversations(limit: int = 50):
    """
    获取对话列表
    
    返回所有对话的列表，按更新时间倒序排列。
    
    Args:
        limit (int): 返回的最大对话数量，默认 50
    
    Returns:
        List[Conversation]: 对话列表
    
    Raises:
        HTTPException: 500 - 数据库操作失败
    
    Example:
        >>> GET /api/conversations?limit=10
        [
            {
                "id": "550e8400-...",
                "title": "Python 学习",
                "created_at": "2024-05-07T10:30:00",
                "updated_at": "2024-05-07T11:00:00",
                "message_count": 5
            },
            ...
        ]
    """
    try:
        return db.get_conversations(limit)
    except Exception as e:
        print(f"[ERROR] Get conversations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Conversation)
def create_conversation(req: ConversationCreate):
    """
    创建新对话
    
    创建一个新的对话记录。
    
    Args:
        req (ConversationCreate): 创建请求，包含标题
    
    Returns:
        Conversation: 新创建的对话对象
    
    Raises:
        HTTPException: 500 - 创建失败
    
    Example:
        >>> POST /api/conversations
        >>> Body: {"title": "Python 学习"}
        {
            "id": "550e8400-...",
            "title": "Python 学习",
            "created_at": "2024-05-07T10:30:00",
            "updated_at": "2024-05-07T10:30:00",
            "message_count": 0
        }
    """
    try:
        conversation_id = db.create_conversation(req.title)
        # 取最新创建的那一个 --- 无需id
        conversations = db.get_conversations(limit=1)
        if conversations:
            return conversations[0]
        raise HTTPException(status_code=500, detail="Failed to create conversation")
    except Exception as e:
        print(f"[ERROR] Create conversation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str):
    """
    获取对话详情
    
    返回指定对话的完整信息，包括所有消息历史。
    
    Args:
        conversation_id (str): 对话 ID
    
    Returns:
        ConversationDetail: 对话详情对象
    
    Raises:
        HTTPException: 404 - 对话不存在
        HTTPException: 500 - 数据库操作失败
    
    Example:
        >>> GET /api/conversations/550e8400-...
        {
            "id": "550e8400-...",
            "title": "Python 学习",
            "created_at": "2024-05-07T10:30:00",
            "updated_at": "2024-05-07T11:00:00",
            "messages": [
                {"role": "user", "content": "你好", ...},
                {"role": "assistant", "content": "你好！", ...}
            ]
        }
    """
    try:
        conversation = db.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Get conversation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{conversation_id}")
def update_conversation(conversation_id: str, req: ConversationUpdate):
    """
    更新对话标题
    
    修改指定对话的标题。
    
    Args:
        conversation_id (str): 对话 ID
        req (ConversationUpdate): 更新请求，包含新标题
    
    Returns:
        dict: {"success": True}
    
    Raises:
        HTTPException: 500 - 更新失败
    
    Example:
        >>> PUT /api/conversations/550e8400-...
        >>> Body: {"title": "Python 进阶学习"}
        {"success": true}
    """
    try:
        db.update_conversation_title(conversation_id, req.title)
        return {"success": True}
    except Exception as e:
        print(f"[ERROR] Update conversation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    """
    删除对话
    
    删除指定对话及其所有消息。
    
    Args:
        conversation_id (str): 对话 ID
    
    Returns:
        dict: {"success": True}
    
    Raises:
        HTTPException: 500 - 删除失败
    
    Example:
        >>> DELETE /api/conversations/550e8400-...
        {"success": true}
    """
    try:
        db.delete_conversation(conversation_id)
        return {"success": True}
    except Exception as e:
        print(f"[ERROR] Delete conversation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
