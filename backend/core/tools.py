import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any

WORKDIR = Path.cwd()


def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR, capture_output=True, timeout=120)
        def decode(b):
            if not b: return ""
            try: return b.decode("utf-8")
            except UnicodeDecodeError: return b.decode("gbk", errors="replace")
        out = (decode(r.stdout) + decode(r.stderr)).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


def run_read(path: str, limit: int = None) -> str:
    try:
        text = safe_path(path).read_text(encoding="utf-8")
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text(encoding="utf-8")
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_compress(reason: str = "") -> str:
    return f"Context compression triggered{': ' + reason if reason else ''}"


def run_load_skill(skill_loader, name: str) -> str:
    return skill_loader.get_content(name)


class ToolHandlerFactory:
    def __init__(self, db=None, conversation_id=None, skill_loader=None, todo_manager=None,
                 base_handlers=None, team_manager=None, message_bus=None):
        self.db = db
        self.conversation_id = conversation_id
        self.skill_loader = skill_loader
        self.todo_manager = todo_manager
        self.base_handlers = base_handlers or {}
        self.team_manager = team_manager
        self.message_bus = message_bus

    def _handle_task_create(self, **kw):
        if self.db and self.conversation_id:
            task = self.db.create_task(
                self.conversation_id, kw["subject"],
                kw.get("description", ""), kw.get("project", ""), kw.get("tags", [])
            )
            return json.dumps(task, ensure_ascii=False, indent=2)
        return "Error: Task system not available"

    def _handle_task_update(self, **kw):
        if self.db:
            task = self.db.update_task(
                kw["task_id"], kw.get("status"),
                kw.get("add_blocked_by"), kw.get("remove_blocked_by")
            )
            return json.dumps(task, ensure_ascii=False, indent=2)
        return "Error: Task system not available"

    def _handle_task_list(self, **kw):
        if self.db and self.conversation_id:
            return self.db.list_tasks(self.conversation_id, kw.get("project_filter"))
        return "Error: Task system not available"

    def _handle_task_get(self, **kw):
        if self.db:
            task = self.db.get_task(kw["task_id"])
            if task:
                return json.dumps(task, ensure_ascii=False, indent=2)
            return f"Error: Task {kw['task_id']} not found"
        return "Error: Task system not available"

    def _handle_task_delete(self, **kw):
        if self.db:
            return json.dumps(self.db.delete_task(kw["task_id"]), ensure_ascii=False, indent=2)
        return "Error: Task system not available"

    def _handle_task_list_all(self, **kw):
        if self.db:
            return self.db.list_all_tasks(kw.get("status_filter"), kw.get("project_filter"))
        return "Error: Task system not available"

    def _handle_spawn_teammate(self, **kw):
        if self.team_manager:
            return self.team_manager.spawn(kw["name"], kw["role"], kw["prompt"])
        return "Error: Team system not available"

    def _handle_list_teammates(self, **kw):
        if self.team_manager:
            return self.team_manager.list_all()
        return "Error: Team system not available"

    def _handle_send_message(self, **kw):
        if self.message_bus:
            return self.message_bus.send("lead", kw["to"], kw["content"])
        return "Error: Message bus not available"

    def _handle_read_inbox(self, **kw):
        if self.message_bus:
            return json.dumps(self.message_bus.read_inbox("lead"), ensure_ascii=False, indent=2)
        return "Error: Message bus not available"

    def _handle_broadcast(self, **kw):
        if self.team_manager and self.message_bus:
            return self.message_bus.broadcast("lead", kw["content"], self.team_manager.member_names())
        return "Error: Team system not available"

    def _handle_shutdown_teammate(self, **kw):
        if self.team_manager:
            return self.team_manager.shutdown_teammate(kw["teammate"])
        return "Error: Team system not available"

    def get_handlers(self) -> Dict[str, Any]:
        return {
            **self.base_handlers,
            "task_create": self._handle_task_create,
            "task_update": self._handle_task_update,
            "task_list": self._handle_task_list,
            "task_get": self._handle_task_get,
            "task_delete": self._handle_task_delete,
            "task_list_all": self._handle_task_list_all,
            "spawn_teammate": self._handle_spawn_teammate,
            "list_teammates": self._handle_list_teammates,
            "send_message": self._handle_send_message,
            "read_inbox": self._handle_read_inbox,
            "broadcast": self._handle_broadcast,
            "shutdown_teammate": self._handle_shutdown_teammate,
        }


def create_base_handlers(skill_loader, todo_manager, subagent_runner):
    handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
        "compress_context": lambda **kw: run_compress(kw.get("reason", "")),
        "load_skill": lambda **kw: run_load_skill(skill_loader, kw["name"]),
        "todo": lambda **kw: todo_manager.update(kw["items"]),
    }
    if subagent_runner:
        handlers["delegate_task"] = lambda **kw: subagent_runner(kw["task"], handlers, kw.get("max_iterations", 30))
    return handlers


def _prop(type_, desc=None, **extra):
    p = {"type": type_}
    if desc:
        p["description"] = desc
    p.update(extra)
    return p


def _tool(name, desc, props, required=None):
    return {
        "name": name,
        "description": desc,
        "input_schema": {
            "type": "object",
            "properties": props,
            **({"required": required} if required else {}),
        },
    }


TOOLS = [
    _tool("bash", "Run a shell command.", {"command": _prop("string")}, ["command"]),

    _tool("read_file", "Read file. Use limit for large files.",
          {"path": _prop("string", "Relative path"), "limit": _prop("integer", "Max lines")},
          ["path"]),

    _tool("write_file", "Write file (creates dirs if needed).",
          {"path": _prop("string", "Relative path"), "content": _prop("string")},
          ["path", "content"]),

    _tool("edit_file", "Replace first occurrence of exact text in file.",
          {"path": _prop("string"), "old_text": _prop("string", "Exact text to find"),
           "new_text": _prop("string", "Replacement")},
          ["path", "old_text", "new_text"]),

    _tool("compress_context", "Compress context to save tokens.",
          {"reason": _prop("string", "Optional reason")}),

    _tool("load_skill", "Load specialized knowledge before tackling unfamiliar topics.",
          {"name": _prop("string", "Skill name")}, ["name"]),

    _tool("todo",
          "Track steps for multi-step tasks. REQUIRED before starting work with 3+ steps. Update after each step.",
          {"items": {
              "type": "array",
              "items": {
                  "type": "object",
                  "properties": {
                      "id": _prop("string"),
                      "text": _prop("string"),
                      "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                  },
                  "required": ["id", "text", "status"],
              },
          }}, ["items"]),

    _tool("delegate_task",
          "Run an isolated subproblem in a fresh-context subagent. Use for research/exploration, not as a substitute for task_create or spawn_teammate.",
          {"task": _prop("string", "Task description"), "max_iterations": _prop("integer", "Default 30")},
          ["task"]),

    _tool("task_create",
          "Create a persistent task (DB-backed). Use for multi-turn work or before spawning teammates.",
          {"subject": _prop("string"), "description": _prop("string", "Optional"),
           "project": _prop("string", "Optional group name"),
           "tags": {"type": "array", "items": {"type": "string"}}},
          ["subject"]),

    _tool("task_update", "Update task status or dependencies.",
          {"task_id": _prop("integer"),
           "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
           "add_blocked_by": {"type": "array", "items": {"type": "integer"}},
           "remove_blocked_by": {"type": "array", "items": {"type": "integer"}}},
          ["task_id"]),

    _tool("task_list", "List tasks in current conversation.",
          {"project_filter": _prop("string", "Optional")}),

    _tool("task_get", "Get a task by ID.",
          {"task_id": _prop("integer")}, ["task_id"]),

    _tool("task_delete", "Soft-delete a task.",
          {"task_id": _prop("integer")}, ["task_id"]),

    _tool("task_list_all", "List tasks across all conversations.",
          {"status_filter": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
           "project_filter": _prop("string", "Optional")}),

    _tool("spawn_teammate",
          "Spawn an autonomous teammate for parallel work. Create tasks first so they can claim from the task board.",
          {"name": _prop("string"), "role": _prop("string"), "prompt": _prop("string")},
          ["name", "role", "prompt"]),

    _tool("list_teammates", "List all teammates and their status.", {}),

    _tool("send_message", "Send a message to a teammate.",
          {"to": _prop("string", "Recipient name"), "content": _prop("string")},
          ["to", "content"]),

    _tool("read_inbox", "Read messages sent to lead.", {}),

    _tool("broadcast", "Send a message to all teammates.",
          {"content": _prop("string")}, ["content"]),

    _tool("shutdown_teammate", "Gracefully shut down a teammate.",
          {"teammate": _prop("string", "Teammate name")}, ["teammate"]),
]
