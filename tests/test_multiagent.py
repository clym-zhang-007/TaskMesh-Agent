#!/usr/bin/env python3
"""
多 Agent 系统测试脚本

测试场景：
1. 创建任务
2. 生成队友
3. 队友自动认领任务
4. 消息通信
5. 监控状态
6. 关闭队友
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.database import Database
from backend.core.agent import agent_loop_stream


async def test_multi_agent():
    """测试多 Agent 协作"""
    
    print("=" * 60)
    print("多 Agent 系统测试")
    print("=" * 60)
    
    # 初始化数据库
    db = Database("test_multiagent.db")
    conversation_id = "test_conv_001"
    
    # 测试场景：创建两个任务，生成两个队友
    test_prompt = """
我需要你帮我测试多 Agent 系统：

1. 创建两个任务：
   - 任务1：创建一个文件 task1.txt，内容是 "Task 1 completed"
   - 任务2：创建一个文件 task2.txt，内容是 "Task 2 completed"

2. 生成两个队友：
   - 队友1：名字 "worker1"，角色 "file creator"
   - 队友2：名字 "worker2"，角色 "file creator"

3. 等待 10 秒，让队友自动认领和执行任务

4. 检查队友状态

5. 读取收件箱

6. 列出所有任务

7. 关闭所有队友

请按照这个流程执行。
"""
    
    messages = [{"role": "user", "content": test_prompt}]
    
    print("\n📤 发送测试请求...\n")
    
    # 执行 Agent 循环
    async for event in agent_loop_stream(messages, conversation_id, db):
        if event['type'] == 'tool_start':
            print(f"🔧 [{event['tool_name']}] 开始执行...")
            if event.get('tool_input'):
                print(f"   参数: {str(event['tool_input'])[:100]}")
        
        elif event['type'] == 'tool_result':
            print(f"✅ [{event['tool_name']}] 完成")
            output = event['output']
            if len(output) > 200:
                print(f"   结果: {output[:200]}...")
            else:
                print(f"   结果: {output}")
            print()
        
        elif event['type'] == 'text':
            print(f"💬 Agent: {event['text']}\n")
        
        elif event['type'] == 'error':
            print(f"❌ 错误: {event['message']}\n")
            break
        
        elif event['type'] == 'done':
            print("✅ 测试完成！")
            break
    
    print("\n" + "=" * 60)
    print("测试结束")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_multi_agent())
