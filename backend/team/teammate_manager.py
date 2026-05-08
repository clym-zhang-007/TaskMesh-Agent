import json
import threading
import time
import subprocess
from pathlib import Path
from anthropic import Anthropic
import os
from dotenv import load_dotenv

load_dotenv(override=True)
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID", "claude-3-5-sonnet-20241022")
WORKDIR = Path.cwd()

POLL_INTERVAL = 5
IDLE_TIMEOUT = 300
_claim_lock = threading.Lock()
STOP_BROADCAST_CONTENT = "STOP_ALL"

TEAMMATE_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write file (creates dirs if needed).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace first occurrence of exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "send_message", "description": "Send a message to a teammate or lead.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
    {"name": "claim_task", "description": "Claim a task from the task board by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "idle", "description": "Enter idle mode when current work is done. Will auto-scan for new tasks.",
     "input_schema": {"type": "object", "properties": {}}},
]


class TeammateManager:
    def __init__(self, team_dir: Path, bus, task_mgr):
        self.team_dir = team_dir
        self.bus = bus
        self.task_mgr = task_mgr
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.team_dir / "config.json"
        self.config = self._load_config()
        self.threads = {}

    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"team_name": "default", "members": []}

    def _save_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8")

    def _find_member(self, name: str):
        return next((m for m in self.config["members"] if m["name"] == name), None)

    def _set_status(self, name: str, status: str):
        if member := self._find_member(name):
            member["status"] = status
            self._save_config()

    def _should_stop(self, msg: dict) -> bool:
        return msg.get("type") == "shutdown_request" or (
            msg.get("type") == "broadcast" and msg.get("content") == STOP_BROADCAST_CONTENT
        )

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find_member(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()
        threading.Thread(target=self._loop, args=(name, role, prompt), daemon=True).start()
        return f"Spawned '{name}' (role: {role})"

    def _loop(self, name: str, role: str, prompt: str):
        sys = f"You are '{name}', role: {role}. Work autonomously, act don't explain. Complete the task, then call idle. In idle mode you auto-scan the task board; claim_task if available. Use send_message to talk to lead or teammates."
        msgs = [{"role": "user", "content": prompt}]

        while True:
            for _ in range(50):
                for msg in self.bus.read_inbox(name):
                    if self._should_stop(msg):
                        self._set_status(name, "shutdown")
                        return
                    msgs.append({"role": "user", "content": f"<msg from='{msg['from']}'>{msg['content']}</msg>"})
                try:
                    resp = client.messages.create(model=MODEL, system=sys, messages=msgs, tools=TEAMMATE_TOOLS, max_tokens=8000)
                except Exception:
                    self._set_status(name, "shutdown")
                    return
                msgs.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason != "tool_use":
                    break
                results, idle_req = [], False
                for b in resp.content:
                    if hasattr(b, "type") and b.type == "tool_use":
                        if b.name == "idle":
                            idle_req, out = True, "Idle"
                        else:
                            out = self._exec(name, b.name, b.input)
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)})
                msgs.append({"role": "user", "content": results})
                if idle_req:
                    break

            self._set_status(name, "idle")
            msgs = []
            resume = False
            for _ in range(IDLE_TIMEOUT // POLL_INTERVAL):
                time.sleep(POLL_INTERVAL)
                if inbox := self.bus.read_inbox(name):
                    for msg in inbox:
                        if self._should_stop(msg):
                            self._set_status(name, "shutdown")
                            return
                        msgs.append({"role": "user", "content": f"<msg from='{msg['from']}'>{msg['content']}</msg>"})
                    resume = True
                    break
                with _claim_lock:
                    if tasks := self.task_mgr.scan_unclaimed_tasks():
                        t = tasks[0]
                        claim_result = self.task_mgr.claim(t["id"], name)
                        if not claim_result.startswith("Error"):
                            msgs.append({"role": "user", "content": f"<auto-claimed>Task #{t['id']}: {t['subject']}\n{t.get('description', '')}</auto-claimed>"})
                            msgs.append({"role": "assistant", "content": f"Claimed task #{t['id']}. Working on it."})
                            resume = True
                            break
            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def _exec(self, sender, tool, inp):
        try:
            if tool == "bash": return self._bash(inp["command"])
            if tool == "read_file": return self._read(inp["path"])
            if tool == "write_file": return self._write(inp["path"], inp["content"])
            if tool == "edit_file": return self._edit(inp["path"], inp["old_text"], inp["new_text"])
            if tool == "send_message": return self.bus.send(sender, inp["to"], inp["content"])
            if tool == "claim_task": return self.task_mgr.claim(inp["task_id"], sender)
        except Exception as e:
            return f"Error: {e}"

    def _safe(self, p):
        path = (WORKDIR / p).resolve()
        if not path.is_relative_to(WORKDIR):
            raise ValueError("Path escape")
        return path

    def _bash(self, cmd):
        if any(d in cmd for d in ["rm -rf /", "sudo"]):
            return "Blocked"
        try:
            r = subprocess.run(cmd, shell=True, cwd=WORKDIR, capture_output=True, timeout=120)
            out = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")
            return out[:5000] or "(no output)"
        except Exception:
            return "Error"

    def _read(self, p):
        try: return self._safe(p).read_text()[:5000]
        except Exception as e: return f"Error: {e}"

    def _write(self, p, c):
        try:
            fp = self._safe(p)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(c)
            return f"Wrote {len(c)} bytes"
        except Exception as e: return f"Error: {e}"

    def _edit(self, p, old, new):
        try:
            fp = self._safe(p)
            c = fp.read_text()
            if old not in c: return "Not found"
            fp.write_text(c.replace(old, new, 1))
            return "Edited"
        except Exception as e: return f"Error: {e}"

    def list_all(self):
        if not self.config["members"]:
            return "No teammates."
        return "\n".join([f"Team: {self.config['team_name']}"] + [
            f"  {m['name']} ({m['role']}): {m['status']}" for m in self.config["members"]
        ])

    def member_names(self):
        return [m["name"] for m in self.config["members"]]

    def shutdown_teammate(self, name):
        self.bus.send("lead", name, "Shutdown", "shutdown_request")
        return f"Shutdown sent to '{name}'"
