"""
子 Agent 模块

实现上下文隔离的子 Agent 功能，用于处理复杂或探索性任务。

核心概念：
- 父 Agent：主 Agent，维护完整的对话历史
- 子 Agent：临时 Agent，拥有独立的干净上下文

工作流程：
    父 Agent                        子 Agent
    +------------------+            +------------------+
    | messages=[...]   |            | messages=[]      | ← 干净上下文
    |                  | dispatch   |                  |
    | tool: delegate   | ---------> | 执行任务         |
    |   task="..."     |            | 调用工具         |
    |                  | summary    | 生成摘要         |
    | result = "..."   | <--------- | 返回结果         |
    +------------------+            +------------------+
              ↓                              ↓
    父上下文保持简洁              子上下文被丢弃

优势：
1. 上下文隔离 - 子任务不污染父上下文
2. Token 节省 - 只返回摘要，不保留中间过程
3. 并行潜力 - 可以同时运行多个子 Agent（未来扩展）
4. 防止混乱 - 复杂任务的细节不会干扰主流程

适用场景：
- 探索性任务（如"分析这个目录的结构"）
- 独立子任务（如"生成测试数据"）
- 复杂操作（如"重构这个模块"）
- 需要多次尝试的任务

Example:
    >>> from backend.team.subagent import run_subagent
    >>> result = run_subagent("分析 backend/ 目录的代码结构")
    >>> print(result)
    "backend/ 目录包含 9 个核心模块，主要功能包括..."
"""

import os
from typing import List, Dict, Any
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

# 初始化 Anthropic 客户端
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID", "claude-3-5-sonnet-20241022")

# 子 Agent 系统提示词（简化版，专注于任务完成）
SUBAGENT_SYSTEM = """You are a coding subagent. Complete the given task efficiently, then provide a clear summary.

Available tools:
- bash: Run shell commands
- read_file: Read file contents
- write_file: Create files
- edit_file: Modify files

Focus on:
1. Complete the task thoroughly
2. Provide a concise summary of what you did
3. Include key findings or results
4. Keep the summary under 500 words

Do NOT:
- Explain every step in detail
- Include unnecessary context
- Repeat information
"""

# 子 Agent 可用工具（基础工具，不包括 delegate_task）
SUBAGENT_TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace exact text in file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"}
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
]


def run_subagent(task: str, tool_handlers: Dict[str, Any], max_iterations: int = 30) -> str:
    """
    运行子 Agent 执行任务
    
    创建独立的消息上下文，执行任务后只返回摘要。
    子 Agent 的中间对话历史会被丢弃，不会污染父 Agent 的上下文。
    
    Args:
        task (str): 任务描述
        tool_handlers (Dict[str, Any]): 工具处理函数映射
        max_iterations (int): 最大循环次数，默认 30
    
    Returns:
        str: 任务执行摘要
    
    Example:
        >>> from backend.core.agent import TOOL_HANDLERS
        >>> result = run_subagent(
        ...     "分析 backend/agent.py 的代码结构",
        ...     TOOL_HANDLERS
        ... )
        >>> print(result)
        "agent.py 包含 7 个工具定义，主要功能包括..."
    """
    # 创建独立的消息上下文
    sub_messages = [{"role": "user", "content": task}]
    
    print(f"[SUBAGENT] Starting task: {task[:80]}...")
    
    # 子 Agent 循环
    for iteration in range(max_iterations):
        try:
            # 调用 LLM
            response = client.messages.create(
                model=MODEL,
                system=SUBAGENT_SYSTEM,
                messages=sub_messages,
                tools=SUBAGENT_TOOLS,
                max_tokens=8000,
            )
            
            # 追加回复到子上下文
            sub_messages.append({"role": "assistant", "content": response.content})
            
            # 如果不再调用工具，任务完成
            if response.stop_reason != "tool_use":
                break
            
            # 执行工具
            results = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    
                    # 通过父 Agent 的工具处理器执行
                    handler = tool_handlers.get(tool_name)
                    if handler:
                        output = handler(**tool_input)
                        print(f"[SUBAGENT] {tool_name}: {str(output)[:100]}...")
                    else:
                        output = f"Unknown tool: {tool_name}"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output)[:50000]  # 限制输出长度
                    })
            
            # 追加工具结果到子上下文
            sub_messages.append({"role": "user", "content": results})
        
        except Exception as e:
            print(f"[SUBAGENT ERROR] {e}")
            return f"Subagent failed: {e}"
    
    # 提取最终文本摘要
    summary = ""
    for block in response.content:
        if hasattr(block, "text") and block.text:
            summary += block.text
    
    result = summary.strip() if summary else "(no summary)"
    print(f"[SUBAGENT] Completed. Summary length: {len(result)} chars")
    
    return result


def run_subagent_async(task: str, tool_handlers: Dict[str, Any], max_iterations: int = 30):
    """
    异步运行子 Agent（未来扩展）
    
    用于并行执行多个子 Agent 任务。
    
    Args:
        task (str): 任务描述
        tool_handlers (Dict[str, Any]): 工具处理函数映射
        max_iterations (int): 最大循环次数
    
    Returns:
        Coroutine: 异步任务
    
    Note:
        当前版本未实现，预留接口
    """
    # 注意：异步版本尚未实现，可作为未来优化方向
    raise NotImplementedError("Async subagent not implemented yet")
