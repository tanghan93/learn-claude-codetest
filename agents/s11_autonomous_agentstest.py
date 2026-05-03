#!/usr/bin/env python3
# Harness: autonomy -- models that find work without being told.
"""
s11_autonomous_agents.py - Autonomous Agents

Idle cycle with task board polling, auto-claiming unclaimed tasks, and
identity re-injection after context compression. Builds on s10's protocols.

    Teammate lifecycle:
    +-------+
    | spawn |
    +---+---+
        |
        v
    +-------+  tool_use    +-------+
    | WORK  | <----------- |  LLM  |
    +---+---+              +-------+
        |
        | stop_reason != tool_use
        v
    +--------+
    | IDLE   | poll every 5s for up to 60s
    +---+----+
        |
        +---> check inbox -> message? -> resume WORK
        |
        +---> scan .tasks/ -> unclaimed? -> claim -> resume WORK
        |
        +---> timeout (60s) -> shutdown

    Identity re-injection after compression:
    messages = [identity_block, ...remaining...]
    "You are 'coder', role: backend, team: my-team"

Key insight: "The agent finds work itself."

s11_autonomous_agents.py - 自主智能体

空闲时自动轮询任务板 → 自动领没人做的任务 → 自动干活
基于 s10 协议（关机、计划审批）

队友生命周期：
创建 → 工作 → 没事干 → 空闲轮询 → 找到任务 → 继续工作
                                 60秒没活 → 自动关机
                
[1] Spawn 生成队友（初始状态: working）
     │
     ▼
┌───────────────────────────────┐
│        【WORK 工作阶段】        │ ←─┐
│ 最多 50 轮循环：                │  │
│   - 读收件箱（inbox）           │  │
│   - 调用 LLM 思考              │  │
│   - 执行工具（bash/read/write…）│  │
│   - 若调用 idle → 退出工作阶段   │  │
└───────────────────┬───────────┘  │
                    │              │
        stop_reason == idle / 非tool_use
                    │                │
                    ▼                │
┌───────────────────────────────┐    │
│        【IDLE 空闲阶段】        │    │
│ 状态设为 idle，开始轮询：        │    │
│ 每 5 秒一次，最多 60 秒（12轮）   │   │
│                               │    │
│  ① 检查收件箱 → 有消息？         │──┐ │
│     └─ 有 → 处理消息 → 回到 WORK│  │ │
│                               │  │ │
│  ② 扫描 .tasks/ → 有未认领任务？ │──┐ │
│     └─ 有 → 自动 claim → 回到 WORK │  │
│                                │     │
│  ③ 60秒都没活 → 自动 shutdown   │     │
└───────────────────────────────┘
"""

from importlib.resources import read_text
import json
import os
import subprocess
import threading   # 多线程：让多个 AI 同时运行
import time
import uuid         # 生成唯一 ID 用于请求追踪
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEFAULT_MODEL
load_dotenv(override=True)

#设置 Anthropic 客户端（使用配置文件中的 API 密钥）

#替换为 DeepSeek 的 Anthropic 客户端，使用环境变量中的 API 密钥和 base URL
#workdir 定义为当前工作目录，供系统提示使用
WORKDIR = Path.cwd()
#* deepseek-chat 和 deepseek-reasoner 对应模型版本不变，
#为 DeepSeek-V3.2 (128K 上下文长度)，与 APP/WEB 版不同。
#deepseek-chat 对应 DeepSeek-V3.2 的非思考模式，
#deepseek-reasoner 对应 DeepSeek-V3.2 的思考模式。
client = Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

MODEL = DEFAULT_MODEL

TEAM_DIR = WORKDIR / ".team"    # 团队配置目录
INBOX_DIR = TEAM_DIR / "inbox"  # 收件箱目录
TASKS_DIR = TEAM_DIR / "tasks"  # 任务目录

POLL_INTERVAL = 5  # 轮询间隔，单位秒
IDLE_TIMEOUT = 60  # 空闲超时时间，单位秒

SYSTEM =  f"You are a team lead at {WORKDIR}. Teammates are autonomous -- they find work themselves."

# 声明所有消息类型，供后续实现使用
VALID_MSG_TYPES = {
    "message",  # 普通文本消息
    "broadcast", # 全员广播消息
    "shutdown_request", # 关机请求消息
    "shutdown_response", # 关机响应消息
    "plan_approval_response", # 计划审批响应消息
}

# -- Request trackers: correlate by request_id --
shutdown_requests = {} ## 关机请求：{req_id: 状态}{request_id: {target: name, status: pending|approved|rejected}}
plan_requests = {}     # # 计划请求：{request_id: {from: name, plan: text, status: pending|approved|rejected}}
_tracker_lock = threading.Lock() # 线程锁，保护请求追踪器的并发访问
_claim_lock = threading.Lock() # 线程锁，保护任务认领的并发访问

# -- MessageBus: JSONL inbox per teammate --
class MessageBus:
    # 初始化 MessageBus，接受收件箱目录路径，确保目录存在
    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True) # 确保收件箱目录存在

    # 发送消息：写入目标队友的 JSONL 文件，包含消息类型和内容
    def send(self, sender: str, to: str, content: str, msg_type: str="message",extra: dict=None)->str:

        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid message type {msg_type}. Valid types: {VALID_MSG_TYPES}"
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg["extra"] = extra
        inbox_path = self.inbox_dir / f"{to}.jsonl"
        with inbox_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"Sent {msg_type} to {to}"

    # 读取收件箱：读取指定队友的 JSONL 文件，返回消息列表，并清空文件
    def read_inbox(self, name: str):
        path = self.inbox_dir / f"{name}.jsonl"
        if not path.exists():
            return []
        messages = []
        for line in path.read_text(encoding="utf-8").strip().splitlines():
            if line:
                messages.append(json.loads(line.strip()))
        path.write_text("", encoding="utf-8") # 读完就清空收件箱
        return messages
    
    # 广播消息：发送消息给所有队友（除发送者外），返回广播结果
    def broadcast(self, sender: str, content: str, teannates: list)->str:
        count = 0
        for teammate in teannates:
            if teammate != sender:
                self.send(sender, teammate, content, msg_type="broadcast")
                count += 1
        return f"Broadcasted message to {count} teammates"

BUS = MessageBus(INBOX_DIR) # 实例化消息总线，供工具处理器使用


# -- Task board scanning --
def scan_unclaimed_tasks() -> list:
    """
    扫描任务板，返回所有未被领任务的列表
    """
    TASKS_DIR.mkdir(exist_ok=True)
    unclaimed = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text(encoding="utf-8"))
        if (task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")
            ):
            
            unclaimed.append(task)
    return unclaimed

def claim_task(task_id:int, owner:str) ->str:
    """
    认领任务：更新任务板，将任务状态设为 "claimed"，并记录认领人
    """
    with _claim_lock:
        path = TASKS_DIR / f"task_{task_id}.json"
        if not path.exists():
            return f"Error: Task {task_id} not found"
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("owner"):
            existing_owner = task.get("owner") or "someone else"
            return f"Error: Task {task_id} is already claimed by {existing_owner}"
        if task.get("status") != "pending":
            return f"Error: Task {task_id} cannot be claimed because it status is '{task.get('status')}'"
        if task.get("blockedBy"):
            return f"Error: Task {task_id} is blocked by other task(s) and cannot be claimed."
        
        task["owner"] = owner
        task["status"] = "in_progress"
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    return f"Task {task_id} claimed by {owner}"

# -- Identity re-injection after compression --
def make_identity_block(name: str, role: str,team_name:str) ->dict:
    """
    生成身份块：包含姓名、角色和团队名称的字典
    """
    return {
        "name": name,
        "role": "user",
        "content":f"<identity>You are '{name}',role: '{role}' on team '{team_name}'. Continue your work.</identity>"

    }

# -- Autonomous TeammateManager --
class TeammateManager:

    # 初始化 TeammateManager，接受团队目录路径，确保目录存在
    # 并加载团队配置
    def __init__(self, team_dir: Path):
        self.team_dir = team_dir
        self.team_dir.mkdir(parents=True, exist_ok=True) # 确保团队目录存在
        self.config_path = self.team_dir / "config.json"
        self.config = self._load_config()
        self.threads = {}
    
    def _load_config(self) -> dict:
        """
        加载团队配置：从取团队配置 JSON 文件，返回配置字典
        """
        if self.config_path.exists():
            return json.load(self.config_path.open("r", encoding="utf-8"))
        return {"team_name": "default","members":[]}
    
    def _save_config(self):
        """
        保存团队配置：将配置字典写入团队配置 JSON 文件
        """
        self.config_path.write_text(json.dumps(self.config, ensure_ascii=False, indent=2))
        
    def _find_member(self, name: str) -> dict:
        """
        查找团队成员：根据姓名查找团队配置中的成员，返回成员字典或 None
        """
        for member in self.config["members"]:
            if member["name"] == name:
                return member
        return None
    
    def _set_status(self, name: str, status: str):
        """
        设置团队成员状态：根据姓名和状态更新团队配置中的成员状态
        """
        member = self._find_member(name)
        if member:
            member["status"] = status
            self._save_config()
    
    def spawn(self, name: str, role: str,prompt:str) -> str:
        """
        启动一个新成员：将姓名、角色和提示词添加到团队配置中，返回成员 ID
        """
        member = self._find_member(name)
        if member:
            if member["status"] == "pending":
                return f"Error: Member {name} is already pending"
            member["status"] = "working"
            member["role"] = role
        else:
            member ={
                "name": name,
                "role": role,
                
                "status": "pending"
            }
            self.config["members"].append(member)
        self._save_config()
        thread = threading.Thread(
            target=self._loop,
            args=(name, role, prompt),
            daemon=True
        )
        self.threads[name] = thread
        thread.start()
        return f"Spawned '{name}' as role:'{role}'"
    
    def _loop(self, name: str, role: str, prompt: str):
        """
        成员工作循环：根据角色和提示词，持续运行成员的工作
        """
        team_name = self.config["team_name"]
        sys_prompt = (
            f"You are '{name}', role: {role}, team: {team_name}, at {WORKDIR}. "
            f"Use idle tool when you have no more work. You will auto-claim new tasks."
        )
        messages = [{"role": "user", "content": prompt}]
        tools = self._teammate_tools()

        while True:
            # -- WORK PHASE: standard agent loop --
            for _ in range(50):
                inbox = BUS.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    response = client.messages.create(
                        model=MODEL,
                        system=sys_prompt,
                        messages=messages,
                        tools=tools,
                        max_tokens=8000,
                    )
                except Exception:
                    self._set_status(name, "idle")
                    return
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason != "tool_use":
                    break
                results = []
                idle_requested = False
                for block in response.content:
                    if block.type == "tool_use":
                        if block.name == "idle":
                            idle_requested = True
                            output = "Entering idle phase. Will poll for new tasks."
                        else:
                            output = self._exec(name, block.name, block.input)
                        try:
                            print(f"  [{name}] {block.name}: {str(output)[:120]}")
                        except UnicodeEncodeError:
                            print(f"  [{name}] {block.name}: (output with non-printable chars)")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(output),
                        })
                messages.append({"role": "user", "content": results})
                if idle_requested:
                    break

            # -- IDLE PHASE: poll for inbox messages and unclaimed tasks --
            self._set_status(name, "idle")
            resume = False
            polls = IDLE_TIMEOUT // max(POLL_INTERVAL, 1)
            for _ in range(polls):
                time.sleep(POLL_INTERVAL)
                inbox = BUS.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
                unclaimed = scan_unclaimed_tasks()
                if unclaimed:
                    task = unclaimed[0]
                    result = claim_task(task["id"], name)
                    if result.startswith("Error:"):
                        continue
                    task_prompt = (
                        f"<auto-claimed>Task #{task['id']}: {task['subject']}\n"
                        f"{task.get('description', '')}</auto-claimed>"
                    )
                    if len(messages) <= 3:
                        messages.insert(0, make_identity_block(name, role, team_name))
                        messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
                    messages.append({"role": "user", "content": task_prompt})
                    messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
                    resume = True
                    break

            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def _exec(self, sender: str, tool_name: str, args: dict) -> str:
        # these base tools are unchanged from s02
        if tool_name == "bash":
            return _run_bash(args["command"])
        if tool_name == "read_file":
            return _run_read(args["path"])
        if tool_name == "write_file":
            return _run_write(args["path"], args["content"])
        if tool_name == "edit_file":
            return _run_edit(args["path"], args["old_text"], args["new_text"])
        if tool_name == "send_message":
            return BUS.send(sender, args["to"], args["content"], args.get("msg_type", "message"))
        if tool_name == "read_inbox":
            return json.dumps(BUS.read_inbox(sender), indent=2)
        if tool_name == "shutdown_response":
            req_id = args["request_id"]
            with _tracker_lock:
                if req_id in shutdown_requests:
                    shutdown_requests[req_id]["status"] = "approved" if args["approve"] else "rejected"
            BUS.send(
                sender, "lead", args.get("reason", ""),
                "shutdown_response", {"request_id": req_id, "approve": args["approve"]},
            )
            return f"Shutdown {'approved' if args['approve'] else 'rejected'}"
        if tool_name == "plan_approval":
            plan_text = args.get("plan", "")
            req_id = str(uuid.uuid4())[:8]
            with _tracker_lock:
                plan_requests[req_id] = {"from": sender, "plan": plan_text, "status": "pending"}
            BUS.send(
                sender, "lead", plan_text, "plan_approval_response",
                {"request_id": req_id, "plan": plan_text},
            )
            return f"Plan submitted (request_id={req_id}). Waiting for approval."
        if tool_name == "claim_task":
            return claim_task(args["task_id"], sender)
        return f"Unknown tool: {tool_name}"

    def _teammate_tools(self) -> list:
        # these base tools are unchanged from s02
        return [
            {"name": "bash", "description": "Run a shell command.",
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file contents.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write content to file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Replace exact text in file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message to a teammate.",
             "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
            {"name": "read_inbox", "description": "Read and drain your inbox.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "shutdown_response", "description": "Respond to a shutdown request.",
             "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["request_id", "approve"]}},
            {"name": "plan_approval", "description": "Submit a plan for lead approval.",
             "input_schema": {"type": "object", "properties": {"plan": {"type": "string"}}, "required": ["plan"]}},
            {"name": "idle", "description": "Signal that you have no more work. Enters idle polling phase.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "claim_task", "description": "Claim a task from the task board by ID.",
             "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
        ]

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


TEAM = TeammateManager(TEAM_DIR)


# -- Base tool implementations (these base tools are unchanged from s02) --
def _safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(
            command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace"
        )
        stdout = r.stdout or ""
        stderr = r.stderr or ""
        out = (stdout + stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def _run_read(path: str, limit: int = None) -> str:
    try:
        lines = _safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def _run_write(path: str, content: str) -> str:
    try:
        fp = _safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"


def _run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = _safe_path(path)
        c = fp.read_text(encoding="utf-8")
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# -- Lead-specific protocol handlers --
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    with _tracker_lock:
        shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send(
        "lead", teammate, "Please shut down gracefully.",
        "shutdown_request", {"request_id": req_id},
    )
    return f"Shutdown request {req_id} sent to '{teammate}'"


def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    with _tracker_lock:
        req = plan_requests.get(request_id)
    if not req:
        return f"Error: Unknown plan request_id '{request_id}'"
    with _tracker_lock:
        req["status"] = "approved" if approve else "rejected"
    BUS.send(
        "lead", req["from"], feedback, "plan_approval_response",
        {"request_id": request_id, "approve": approve, "feedback": feedback},
    )
    return f"Plan {req['status']} for '{req['from']}'"


def _check_shutdown_status(request_id: str) -> str:
    with _tracker_lock:
        return json.dumps(shutdown_requests.get(request_id, {"error": "not found"}))


# -- Lead tool dispatch (14 tools) --
TOOL_HANDLERS = {
    "bash":              lambda **kw: _run_bash(kw["command"]),
    "read_file":         lambda **kw: _run_read(kw["path"], kw.get("limit")),
    "write_file":        lambda **kw: _run_write(kw["path"], kw["content"]),
    "edit_file":         lambda **kw: _run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "spawn_teammate":    lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":    lambda **kw: TEAM.list_all(),
    "send_message":      lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":        lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":         lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request":  lambda **kw: handle_shutdown_request(kw["teammate"]),
    "shutdown_response": lambda **kw: _check_shutdown_status(kw.get("request_id", "")),
    "plan_approval":     lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
    "idle":              lambda **kw: "Lead does not idle.",
    "claim_task":        lambda **kw: claim_task(kw["task_id"], "lead"),
}

# these base tools are unchanged from s02
TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "spawn_teammate", "description": "Spawn an autonomous teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send a message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "shutdown_response", "description": "Check shutdown request status.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}}, "required": ["request_id"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
    {"name": "idle", "description": "Enter idle state (for lead -- rarely used).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_task", "description": "Claim a task from the board by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
]


def agent_loop(messages: list):
    while True:
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({
                "role": "user",
                "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>",
            })
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    output = f"Error: {e}"
                print(f"> {block.name}:")
                print(str(output)[:200])
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms11 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        if query.strip() == "/tasks":
            TASKS_DIR.mkdir(exist_ok=True)
            for f in sorted(TASKS_DIR.glob("task_*.json")):
                t = json.loads(f.read_text())
                marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
                owner = f" @{t['owner']}" if t.get("owner") else ""
                print(f"  {marker} #{t['id']}: {t['subject']}{owner}")
            continue
        history.append({"role": "user", "content": query})
        agent_loop(history)
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()
            
        
            

