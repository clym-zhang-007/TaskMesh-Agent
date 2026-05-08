"""
数据 Schema 定义

使用 Pydantic 定义所有 API 请求、响应以及核心数据结构。
提供自动数据验证、序列化和文档生成功能。

Schema 分类：
1. 消息模型 (Message) - 单条消息
2. 工具执行模型 (ToolExecution) - 工具调用记录
3. 聊天请求/响应 (ChatRequest, ChatResponse) - 聊天接口
4. 对话模型 (Conversation, ConversationDetail) - 对话管理
5. 对话操作 (ConversationCreate, ConversationUpdate) - CRUD 操作

说明：
- 该模块定义的是数据结构与接口契约
- 不负责存储实现，因此放在 schema/
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """消息模型。"""
    role: str = Field(..., description="消息角色：'user' 或 'assistant'")
    content: str = Field(..., description="消息内容")
    is_tool_call: bool = Field(default=False, description="是否为工具调用")
    is_tool_output: bool = Field(default=False, description="是否为工具输出")
    is_error: bool = Field(default=False, description="是否为错误消息")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    full_output: Optional[str] = Field(default=None, description="完整输出（未截断）")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")


class ToolExecution(BaseModel):
    """工具执行记录。"""
    command: str = Field(..., description="执行的命令")
    output: str = Field(..., description="执行结果")


class ChatRequest(BaseModel):
    """聊天请求。"""
    message: str = Field(..., description="用户消息", min_length=1)
    conversation_id: Optional[str] = Field(default=None, description="对话 ID（可选）")


class ChatResponse(BaseModel):
    """聊天响应。"""
    text: str = Field(..., description="Agent 回复")
    tools: List[ToolExecution] = Field(default=[], description="工具执行记录")
    conversation_id: str = Field(..., description="对话 ID")


class Conversation(BaseModel):
    """对话模型。"""
    id: str = Field(..., description="对话 ID")
    title: str = Field(..., description="对话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    message_count: int = Field(default=0, description="消息数量")


class ConversationDetail(BaseModel):
    """对话详情。"""
    id: str = Field(..., description="对话 ID")
    title: str = Field(..., description="对话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    messages: List[Message] = Field(default=[], description="消息列表")


class ConversationCreate(BaseModel):
    """创建对话请求。"""
    title: Optional[str] = Field(default="新对话", description="对话标题")


class ConversationUpdate(BaseModel):
    """更新对话请求。"""
    title: str = Field(..., description="对话标题", min_length=1)
