"""
上下文管理模块

提供多层次的上下文压缩策略，确保 Agent 可以处理长对话。

压缩策略：
1. 历史记录压缩 - 加载历史对话时，剔除工具记录并摘要旧消息
2. 微压缩（Layer 1）- 每轮调用前，删除旧的工具记录
3. 自动压缩（Layer 2）- Token 超过阈值时，摘要旧消息
4. 手动压缩（Layer 3）- 用户触发的压缩

"""

import os
from typing import List, Dict, Any
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

# 初始化 Anthropic 客户端
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID", "claude-3-5-sonnet-20241022")

# 配置参数
KEEP_RECENT = 20  # 保留最近的消息数量
TOKEN_THRESHOLD = 80000  # 触发自动压缩的 token 阈值


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    估算消息列表的 token 数量
    
    使用粗略估算：约 4 个字符 = 1 token
    
    Args:
        messages: 消息列表
    
    Returns:
        int: 估算的 token 数量
    
    Example:
        >>> messages = [{"role": "user", "content": "Hello"}]
        >>> estimate_tokens(messages)
        125
    """
    return len(str(messages)) // 4


def summarize_messages(messages: List[Dict[str, Any]]) -> str:
    """
    调用 LLM 对消息列表进行摘要
    
    生成简洁的摘要，保留关键信息：
    - 完成了什么任务
    - 当前状态
    - 重要决策
    
    Args:
        messages: 需要摘要的消息列表
    
    Returns:
        str: 摘要文本
    
    Example:
        >>> messages = [{"role": "user", "content": "创建文件"}, ...]
        >>> summary = summarize_messages(messages)
        >>> print(summary)
        "用户要求创建文件，已完成..."
    """
    # 将消息转换为文本（限制长度避免超出限制）
    conversation_text = str(messages)[-80000:]
    
    try:
        response = client.messages.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "请对以下对话进行摘要，用于保持上下文连贯性。包括：\n"
                    "1) 完成了什么任务\n"
                    "2) 当前状态\n"
                    "3) 做出的关键决策\n"
                    "请简洁但保留关键细节。\n\n"
                    f"{conversation_text}"
                )
            }],
            max_tokens=2000,
        )
        
        # 提取摘要文本
        summary = next(
            (block.text for block in response.content if hasattr(block, "text")),
            "无法生成摘要"
        )
        return summary
    
    except Exception as e:
        return f"摘要生成失败: {str(e)}"


def compress_for_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    压缩历史记录（场景 1：从数据库加载历史对话）
    
    策略：
    1. 剔除所有工具调用和工具输出
    2. 保留最近 20 条原始消息
    3. 摘要 20 条之前的所有消息
    
    Args:
        messages: 完整的消息历史（包含工具记录）
    
    Returns:
        List[Dict[str, Any]]: 压缩后的消息列表
    
    Example:
        >>> messages = [
        ...     {"role": "user", "content": "任务1"},
        ...     {"role": "assistant", "content": "回复1"},
        ...     # ... 很多消息 ...
        ...     {"role": "user", "content": "任务30"},
        ... ]
        >>> compressed = compress_for_history(messages)
        >>> len(compressed)  # 摘要 + 最近 20 条
        21
    """
    if len(messages) <= KEEP_RECENT:
        return messages
    
    # 保留最近的消息
    recent = messages[-KEEP_RECENT:]
    
    # 摘要旧消息
    old = messages[:-KEEP_RECENT]
    if old:
        summary_text = summarize_messages(old)
        summary_message = {
            "role": "user",
            "content": f"[对话历史摘要]\n\n{summary_text}"
        }
        return [summary_message] + recent
    
    return recent


def compress_micro(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    微压缩（Layer 1：每轮调用前）
    
    策略：
    1. 保留最近 20 条消息（不管是否为工具）
    2. 删除 20 条之前的消息中的工具记录
    
    Args:
        messages: 当前消息列表
    
    Returns:
        List[Dict[str, Any]]: 压缩后的消息列表
    
    Example:
        >>> messages = [
        ...     {"role": "user", "content": "任务1"},
        ...     {"role": "assistant", "content": [{"type": "tool_use", ...}]},
        ...     {"role": "user", "content": [{"type": "tool_result", ...}]},
        ...     # ... 很多消息 ...
        ... ]
        >>> compressed = compress_micro(messages)
        # 旧的工具记录被删除，保留最近 20 条
    """
    if len(messages) <= KEEP_RECENT:
        return messages
    
    # 保留最近的消息
    recent = messages[-KEEP_RECENT:]
    
    # 过滤旧消息：删除工具相关的消息
    old = messages[:-KEEP_RECENT]
    old_filtered = []
    
    for msg in old:
        # 保留用户的文本消息
        if msg["role"] == "user" and isinstance(msg.get("content"), str):
            old_filtered.append(msg)
        # 保留助手的文本回复（不包含工具调用）
        elif msg["role"] == "assistant":
            content = msg.get("content")
            # 如果是字符串，保留
            if isinstance(content, str):
                old_filtered.append(msg)
            # 如果是列表，检查是否只包含文本
            elif isinstance(content, list):
                has_text = any(
                    hasattr(block, "text") or (isinstance(block, dict) and block.get("type") == "text")
                    for block in content
                )
                has_tool = any(
                    hasattr(block, "type") and block.type == "tool_use" or
                    (isinstance(block, dict) and block.get("type") == "tool_use")
                    for block in content
                )
                # 只有文本，没有工具调用，保留
                if has_text and not has_tool:
                    old_filtered.append(msg)
    
    return old_filtered + recent


def compress_auto(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    自动压缩（Layer 2：Token 超过阈值时）
    
    策略：
    1. 保留最近 20 条消息
    2. 摘要 20 条之前的所有消息
    3. 组合：[摘要] + [最近 20 条]
    
    Args:
        messages: 当前消息列表
    
    Returns:
        List[Dict[str, Any]]: 压缩后的消息列表
    
    Example:
        >>> messages = [很多消息...]
        >>> if estimate_tokens(messages) > TOKEN_THRESHOLD:
        ...     messages = compress_auto(messages)
    """
    if len(messages) <= KEEP_RECENT:
        return messages
    
    # 保留最近的消息
    recent = messages[-KEEP_RECENT:]
    
    # 摘要旧消息
    old = messages[:-KEEP_RECENT]
    summary_text = summarize_messages(old)
    
    summary_message = {
        "role": "user",
        "content": f"[对话已压缩]\n\n{summary_text}"
    }
    
    return [summary_message] + recent


def should_compress(messages: List[Dict[str, Any]]) -> bool:
    """
    判断是否需要压缩
    
    Args:
        messages: 当前消息列表
    
    Returns:
        bool: 是否需要压缩
    
    Example:
        >>> messages = [很多消息...]
        >>> if should_compress(messages):
        ...     messages = compress_auto(messages)
    """
    return estimate_tokens(messages) > TOKEN_THRESHOLD
