"""
TodoManager 模块

内存级任务清单管理器，用于单次对话中的短期任务追踪。

核心功能：
- 任务状态管理（pending、in_progress、completed）
- 任务列表校验（最多 20 条，同时只能 1 条 in_progress）
- 人类可读的任务列表渲染
- 进度统计

使用场景：
- 适合 3-5 步的简单任务
- 单次对话内的任务追踪
- 不需要持久化的临时任务

与 TaskManager 的区别：
- TodoManager：内存级，短期，单次对话
- TaskManager：持久化，长期，跨对话

说明：
- 该模块属于 Agent 编排过程中的短期任务机制
- 因此放在 core/，而不是通用 utils/

Example:
    >>> from backend.core.todo_manager import TodoManager
    >>> todo = TodoManager()
    >>> result = todo.update([
    ...     {"id": "1", "text": "读取配置", "status": "completed"},
    ...     {"id": "2", "text": "分析代码", "status": "in_progress"},
    ...     {"id": "3", "text": "生成报告", "status": "pending"}
    ... ])
    >>> print(result)
    [x] #1: 读取配置
    [>] #2: 分析代码
    [ ] #3: 生成报告
    
    (1/3 completed)
"""


class TodoManager:
    """
    内存级任务清单管理器
    
    用于单次对话中的短期任务追踪。支持三种状态：
    - pending（待办）：任务尚未开始
    - in_progress（进行中）：任务正在执行
    - completed（已完成）：任务已完成
    
    特点：
    - 内存存储，对话结束后清空
    - 适合 3-5 步的简单任务
    - 最多 20 条任务
    - 同时只能有 1 条 in_progress
    
    Attributes:
        items (list): 任务列表，每个任务包含 id、text、status
    """
    
    def __init__(self):
        """初始化空的任务列表"""
        self.items = []
    
    def update(self, items: list) -> str:
        """更新任务列表并返回渲染后的文本。"""
        if len(items) > 20:
            raise ValueError("Max 20 todos allowed")
        
        validated = []
        in_progress_count = 0
        
        for i, item in enumerate(items):
            text = str(item.get("text", "")).strip()
            status = str(item.get("status", "pending")).lower()
            item_id = str(item.get("id", str(i + 1)))
            
            if not text:
                raise ValueError(f"Item {item_id}: text required")
            
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {item_id}: invalid status '{status}'")
            
            if status == "in_progress":
                in_progress_count += 1
            
            validated.append({
                "id": item_id,
                "text": text,
                "status": status
            })
        
        if in_progress_count > 1:
            raise ValueError("At most one todo can be in_progress")
        
        self.items = validated
        return self.render()
    
    def render(self) -> str:
        """将任务列表渲染为人类可读文本。"""
        if not self.items:
            return "No todos"
        
        lines = []
        completed = 0
        
        for item in self.items:
            status = item["status"]
            if status == "completed":
                prefix = "[x]"
                completed += 1
            elif status == "in_progress":
                prefix = "[>]"
            else:
                prefix = "[ ]"
            lines.append(f"{prefix} #{item['id']}: {item['text']}")
        
        lines.append("")
        lines.append(f"({completed}/{len(self.items)} completed)")
        return "\n".join(lines)
