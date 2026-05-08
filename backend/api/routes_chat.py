"""
聊天路由模块（流式响应）

提供基于 Server-Sent Events (SSE) 的流式聊天接口。
实时推送工具执行过程，提供流畅的用户体验。
"""

import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.schema.models import ChatRequest, Message
from backend.storage.database import Database
from backend.core.agent import agent_loop_stream, stop_all_teammates
from backend.core.context_manager import compress_for_history

router = APIRouter(prefix="/api", tags=["chat"])

db: Database = None


def init_db(database: Database):
    global db
    db = database


@router.post("/chat")
async def chat_stream(req: ChatRequest):
    async def generate():
        conversation_id = None
        task_interrupted = True
        try:
            if not req.conversation_id:
                conversation_id = db.create_conversation()
            else:
                conversation_id = req.conversation_id

            user_message = Message(
                role="user",
                content=req.message,
                created_at=datetime.now()
            )
            db.add_message(conversation_id, user_message)

            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"

            conversation = db.get_conversation(conversation_id)
            if not conversation:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Conversation not found'})}\n\n"
                return

            messages = []
            for msg in conversation.messages:
                if msg.role == "user" or (msg.role == "assistant" and not msg.is_tool_call and not msg.is_tool_output):
                    messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })

            if len(messages) > 1:
                messages = compress_for_history(messages)

            task_interrupted = True
            async for event in agent_loop_stream(messages, conversation_id, db):
                event_type = event.get('type')

                if event_type == 'tool_start':
                    tool_name = event.get('tool_name')
                    tool_input = event.get('tool_input')

                    if tool_name == 'bash':
                        cmd = tool_input.get('command', '')
                        cmd_message = Message(
                            role="assistant",
                            content=f"$ {cmd}",
                            is_tool_call=True,
                            tool_name=tool_name,
                            created_at=datetime.now()
                        )
                    else:
                        cmd_str = f"{tool_name}({', '.join(f'{k}={repr(v)[:50]}' for k, v in tool_input.items())})"
                        cmd_message = Message(
                            role="assistant",
                            content=cmd_str,
                            is_tool_call=True,
                            tool_name=tool_name,
                            created_at=datetime.now()
                        )
                    db.add_message(conversation_id, cmd_message)
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == 'tool_result':
                    tool_name = event.get('tool_name')
                    output = event.get('output', '')

                    if output and output != "(no output)":
                        output_message = Message(
                            role="assistant",
                            content=output[:200] + ('...' if len(output) > 200 else ''),
                            is_tool_output=True,
                            tool_name=tool_name,
                            full_output=output,
                            created_at=datetime.now()
                        )
                        db.add_message(conversation_id, output_message)

                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == 'text':
                    text = event.get('text', '')
                    if text:
                        assistant_message = Message(
                            role="assistant",
                            content=text,
                            created_at=datetime.now()
                        )
                        db.add_message(conversation_id, assistant_message)
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == 'done':
                    task_interrupted = False
                    if len(conversation.messages) == 1:
                        db.auto_generate_title(conversation_id)
                    yield f"data: {json.dumps(event)}\n\n"

        except GeneratorExit:
            print(f"[INTERRUPT] Client disconnected for conversation {conversation_id}")
            stop_all_teammates()
            if conversation_id and task_interrupted:
                interrupt_message = Message(
                    role="assistant",
                    content="⏹️ [任务已中断，已广播通知所有子 Agent 停止]",
                    created_at=datetime.now()
                )
                db.add_message(conversation_id, interrupt_message)

        except Exception as e:
            print(f"[ERROR] Chat failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
