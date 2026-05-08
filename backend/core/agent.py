import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from anthropic import Anthropic
from dotenv import load_dotenv

from backend.core.context_manager import compress_micro, compress_auto, should_compress
from backend.core.skill_loader import SkillLoader
from backend.core.todo_manager import TodoManager
from backend.team.subagent import run_subagent
from backend.core.task_manager import TaskManager
from backend.team.message_bus import MessageBus
from backend.team.teammate_manager import TeammateManager
from backend.core.tools import ToolHandlerFactory, create_base_handlers, TOOLS

load_dotenv(override=True)

client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID", "claude-3-5-sonnet-20241022")
WORKDIR = Path.cwd()
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "50"))
SKILL_LOADER = SkillLoader(WORKDIR / "skills")
TODO_MANAGER = TodoManager()
TEAM_DIR = WORKDIR / ".team"
BUS = MessageBus(TEAM_DIR / "inbox")
TASK_MGR = None
TEAM = None


def stop_all_teammates() -> str:
    if TEAM is None:
        return "No team."
    recipients = TEAM.member_names()
    return BUS.broadcast("lead", "STOP_ALL", recipients) if recipients else "No active teammates."


def init_team_components(db):
    global TASK_MGR, TEAM
    if TASK_MGR is None and db:
        TASK_MGR = TaskManager(db)
        TEAM = TeammateManager(TEAM_DIR, BUS, TASK_MGR)


SYSTEM = f"""You are a coding agent at {WORKDIR}. Use tools to complete tasks. Act, don't explain.

Rules:
- 3+ steps → call todo FIRST, keep it updated throughout
- Multi-turn / multiple deliverables → use task_create
- Parallel work with distinct roles → task_create per stream, then spawn_teammate
- Isolated exploration → delegate_task
- Always read files before editing

When to use what:
- todo: short-term step tracking (single conversation, 3+ steps)
- task_create/task_update/task_list: persistent work across turns
- spawn_teammate: parallel execution (create tasks first so they can claim them)
- delegate_task: isolated subproblem with fresh context

Available skills: {SKILL_LOADER.get_descriptions()}"""


async def agent_loop_stream(messages: List[Dict[str, Any]], conversation_id: str = None, db=None):
    if db:
        init_team_components(db)

    base_handlers = create_base_handlers(SKILL_LOADER, TODO_MANAGER, run_subagent)
    factory = ToolHandlerFactory(db, conversation_id, SKILL_LOADER, TODO_MANAGER, base_handlers, TEAM, BUS)
    tool_handlers = factory.get_handlers()

    iteration_count = 0
    rounds_since_todo_update = 0
    manual_compress_triggered = False

    while True:
        iteration_count += 1
        if iteration_count > MAX_ITERATIONS:
            yield {"type": "error", "message": f"Max iterations ({MAX_ITERATIONS}) reached."}
            return

        try:
            messages[:] = compress_micro(messages)

            if should_compress(messages):
                messages[:] = compress_auto(messages)
                yield {"type": "text", "text": "[Context compressed]"}

            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                system=SYSTEM,
                messages=messages,
                tools=TOOLS,
                max_tokens=8000,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            results = []
            used_todo = False
            for block in response.content:
                if not (hasattr(block, "type") and block.type == "tool_use"):
                    continue

                tool_name = block.name
                tool_input = block.input

                if tool_name == "compress_context":
                    manual_compress_triggered = True
                if tool_name == "todo":
                    used_todo = True

                yield {"type": "tool_start", "tool_name": tool_name, "tool_input": tool_input}

                handler = tool_handlers.get(tool_name)
                if handler:
                    output = await asyncio.to_thread(handler, **tool_input)
                else:
                    output = f"Unknown tool: {tool_name}"

                yield {"type": "tool_result", "tool_name": tool_name, "output": output}
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})

            rounds_since_todo_update = 0 if used_todo else rounds_since_todo_update + 1
            if rounds_since_todo_update >= 3 and TODO_MANAGER.items:
                results.append({"type": "text", "text": "<reminder>Update todos.</reminder>"})

            messages.append({"role": "user", "content": results})

            if manual_compress_triggered:
                messages[:] = compress_auto(messages)
                yield {"type": "text", "text": "[Context compressed]"}
                manual_compress_triggered = False

        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

    text = "".join(
        block.text for block in response.content if hasattr(block, "text") and block.text
    ).strip()

    if text:
        yield {"type": "text", "text": text}

    yield {"type": "done"}
