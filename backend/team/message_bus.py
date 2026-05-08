"""
消息总线模块

基于 JSONL 文件的队友间通信系统，支持：
1. 点对点消息传递（每个 agent 有独立的收件箱）
2. 广播消息（发送给所有队友）
3. 消息类型管理（message, broadcast, shutdown_request 等）
4. 收件箱排空机制（读取后自动清空）

设计理念：
- 每个 agent 有独立的 .jsonl 收件箱文件
- 消息持久化到文件，不依赖内存
- 支持多线程并发访问（文件锁保护）
- 消息格式统一，便于扩展

收件箱结构：
    .team/inbox/
        lead.jsonl      # 主管的收件箱
        coder.jsonl     # coder 队友的收件箱
        tester.jsonl    # tester 队友的收件箱

消息格式：
    {
        "type": "message",           # 消息类型
        "from": "lead",              # 发送者
        "content": "开始执行任务",    # 消息内容
        "timestamp": 1234567890.123, # 时间戳
        "extra_field": "..."         # 可选的额外字段
    }

合法消息类型：
- message: 普通消息
- broadcast: 广播消息
- shutdown_request: 关闭请求
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any


# 合法消息类型集合
VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
}


class MessageBus:
    """
    消息总线
    
    管理 agent 之间的消息传递，每个 agent 有独立的收件箱文件。
    
    Attributes:
        inbox_dir (Path): 收件箱目录路径
    
    Example:
        >>> bus = MessageBus(Path(".team/inbox"))
        >>> bus.send("lead", "coder", "开始编码")
        >>> messages = bus.read_inbox("coder")
    """
    
    def __init__(self, inbox_dir: Path):
        """
        初始化消息总线
        
        Args:
            inbox_dir (Path): 收件箱目录路径
        """
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
    
    def send(self, sender: str, to: str, content: str, 
             msg_type: str = "message", extra: dict = None) -> str:
        """
        发送消息
        
        将消息追加到接收者的收件箱文件（JSONL 格式）。
        
        Args:
            sender (str): 发送者名称
            to (str): 接收者名称
            content (str): 消息内容
            msg_type (str): 消息类型，默认为 "message"
            extra (dict): 可选的额外字段（如 request_id）
        
        Returns:
            str: 成功消息或错误信息
        
        Example:
            >>> bus.send("lead", "coder", "开始编码", "message")
            "Sent message from lead to coder"
            >>> 
            >>> bus.send("lead", "coder", "请关闭", "shutdown_request", 
            ...          extra={"request_id": "abc123"})
            "Sent shutdown_request from lead to coder"
        """
        # 验证消息类型
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid message type '{msg_type}'. Valid types: {VALID_MSG_TYPES}"
        
        # 构造消息对象
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        
        # 合并额外字段
        if extra:
            msg.update(extra)
        
        # 追加到收件箱文件
        inbox_path = self.inbox_dir / f"{to}.jsonl"
        try:
            with open(inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            return f"Sent {msg_type} from {sender} to {to}"
        except Exception as e:
            return f"Error: Failed to send message: {e}"
    
    def read_inbox(self, name: str) -> List[Dict[str, Any]]:
        """
        读取并清空收件箱
        
        读取指定 agent 的所有消息，然后清空收件箱文件。
        这是"排空"（drain）模式，确保消息只被处理一次。
        
        Args:
            name (str): Agent 名称
        
        Returns:
            List[Dict[str, Any]]: 消息列表，如果收件箱为空则返回空列表
        
        Example:
            >>> messages = bus.read_inbox("coder")
            >>> for msg in messages:
            ...     print(f"{msg['from']}: {msg['content']}")
        """
        inbox_path = self.inbox_dir / f"{name}.jsonl"
        
        # 如果收件箱文件不存在，返回空列表
        if not inbox_path.exists():
            return []
        
        try:
            # 读取所有消息
            messages = []
            content = inbox_path.read_text(encoding="utf-8").strip()
            if content:
                for line in content.splitlines():
                    if line:
                        messages.append(json.loads(line))
            
            # 清空收件箱
            inbox_path.write_text("", encoding="utf-8")
            
            return messages
        except Exception as e:
            print(f"[ERROR] Failed to read inbox for {name}: {e}")
            return []
    
    def broadcast(self, sender: str, content: str, recipients: List[str]) -> str:
        """
        广播消息
        
        向多个接收者发送相同的消息（不包括发送者自己）。
        
        Args:
            sender (str): 发送者名称
            content (str): 消息内容
            recipients (List[str]): 接收者名称列表
        
        Returns:
            str: 成功消息，包含发送数量
        
        Example:
            >>> bus.broadcast("lead", "开始工作", ["coder", "tester", "reviewer"])
            "Broadcast to 3 teammates"
        """
        count = 0
        for name in recipients:
            if name != sender:  # 不发送给自己
                self.send(sender, to=name, content=content, msg_type="broadcast")
                count += 1
        return f"Broadcast to {count} teammates: {recipients}"
    
    def peek_inbox(self, name: str) -> List[Dict[str, Any]]:
        """
        查看收件箱（不清空）
        
        读取指定 agent 的所有消息，但不清空收件箱。
        用于调试或监控，不影响正常的消息处理流程。
        
        Args:
            name (str): Agent 名称
        
        Returns:
            List[Dict[str, Any]]: 消息列表
        
        Example:
            >>> messages = bus.peek_inbox("coder")
            >>> print(f"收件箱有 {len(messages)} 条消息")
        """
        inbox_path = self.inbox_dir / f"{name}.jsonl"
        
        if not inbox_path.exists():
            return []
        
        try:
            messages = []
            content = inbox_path.read_text(encoding="utf-8").strip()
            if content:
                for line in content.splitlines():
                    if line:
                        messages.append(json.loads(line))
            return messages
        except Exception as e:
            print(f"[ERROR] Failed to peek inbox for {name}: {e}")
            return []
    
    def has_messages(self, name: str) -> bool:
        """
        检查收件箱是否有消息
        
        快速检查指定 agent 的收件箱是否为空。
        
        Args:
            name (str): Agent 名称
        
        Returns:
            bool: 如果有消息返回 True，否则返回 False
        
        Example:
            >>> if bus.has_messages("coder"):
            ...     messages = bus.read_inbox("coder")
        """
        inbox_path = self.inbox_dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return False
        try:
            content = inbox_path.read_text(encoding="utf-8").strip()
            return bool(content)
        except Exception:
            return False
    
    def clear_inbox(self, name: str):
        """
        清空收件箱
        
        删除指定 agent 的所有消息，不返回消息内容。
        
        Args:
            name (str): Agent 名称
        
        Example:
            >>> bus.clear_inbox("coder")
        """
        inbox_path = self.inbox_dir / f"{name}.jsonl"
        if inbox_path.exists():
            inbox_path.write_text("", encoding="utf-8")
        return f"Cleared inbox for {name}"
    
    def list_inboxes(self) -> List[str]:
        """
        列出所有收件箱
        
        返回所有存在的收件箱名称列表。
        
        Returns:
            List[str]: Agent 名称列表
        
        Example:
            >>> inboxes = bus.list_inboxes()
            >>> print(inboxes)
            ['lead', 'coder', 'tester']
        """
        return [f.stem for f in self.inbox_dir.glob("*.jsonl")] or []
