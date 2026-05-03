#!/usr/bin/env python3
# Harness: protocols -- structured handshakes between models.
from flask import Flask
"""
s10_team_protocols.py - Team Protocols

Shutdown protocol and plan approval protocol, both using the same
request_id correlation pattern. Builds on s09's team messaging.

    Shutdown FSM: pending -> approved | rejected

    Lead                              Teammate
    +---------------------+          +---------------------+
    | shutdown_request     |          |                     |
    | {                    | -------> | receives request    |
    |   request_id: abc    |          | decides: approve?   |
    | }                    |          |                     |
    +---------------------+          +---------------------+
                                             |
    +---------------------+          +-------v-------------+
    | shutdown_response    | <------- | shutdown_response   |
    | {                    |          | {                   |
    |   request_id: abc    |          |   request_id: abc   |
    |   approve: true      |          |   approve: true     |
    | }                    |          | }                   |
    +---------------------+          +---------------------+
            |
            v
    status -> "shutdown", thread stops

    Plan approval FSM: pending -> approved | rejected

    Teammate                          Lead
    +---------------------+          +---------------------+
    | plan_approval        |          |                     |
    | submit: {plan:"..."}| -------> | reviews plan text   |
    +---------------------+          | approve/reject?     |
                                     +---------------------+
                                             |
    +---------------------+          +-------v-------------+
    | plan_approval_resp   | <------- | plan_approval       |
    | {approve: true}      |          | review: {req_id,    |
    +---------------------+          |   approve: true}     |
                                     +---------------------+

    Trackers: {request_id: {"target|from": name, "status": "pending|..."}}

Key insight: "Same request_id correlation pattern, two domains."

s10_team_protocols.py - 团队协议

新增两个核心协议：
1. 安全关机协议（Shutdown Protocol）
┌─────────── Lead（领导） ───────────┐
│                                       │
│ 1. 用户："关闭 alice"                │
│ 2. LLM → 调用 shutdown_request      │
│                                       │
│ 3. 生成唯一 req_id（如 abc123）      │
│ 4. 记录：                             │
│    shutdown_requests[req_id] = {     │
│      target: "alice", status: pending│
│    }                                  │
│                                       │
│ 5. 发消息 → alice.jsonl              │
│    type: shutdown_request             │
│    { req_id: "abc123" }              │
│                    │                  │
└────────────────────┼─────────────────┘
                     │
                     ▼
┌────────── Teammate（alice） ──────────┐
│                                         │
│ 6. _teammate_loop 读取收件箱           │
│ 7. 收到 shutdown_request               │
│    → 加入对话上下文                     │
│                                         │
│ 8. LLM 决定：批准 or 拒绝？             │
│                                         │
│ 9. 调用工具：shutdown_response         │
│    { req_id: "abc123", approve: bool }│
│                    │                    │
└────────────────────┼───────────────────┘
                     │
                     ▼
┌─────────── Lead（领导） ───────────┐
│                                       │
│ 10. 收到 shutdown_response           │
│ 11. 按 req_id 匹配请求：              │
│     shutdown_requests[req_id].status │
│     → approved / rejected             │
│                                       │
│ 12. 如果 approve = true：             │
│     → 标记请求为 approved             │
│                                       │
└─────────────────────────────────────┘
                     │
                     ▼
┌────────── Teammate（alice） ──────────┐
│                                         │
│ 13. 本轮工具执行完毕（含保存文件等）   │
│ 14. should_exit = true                 │
│ 15. 退出循环，不再接收新任务           │
│ 16. 更新 config.json：status=shutdown │
│ 17. 线程自然结束 ✅                     │
└───────────────────────────────────────┘
2. 计划审批协议（Plan Approval Protocol）
┌────────── Teammate（队友，如 alice） ──────────┐
│                                               │
│ 1. 执行任务前需重大操作（如批量修改文件）     │
│ 2. LLM → 调用 plan_approval 工具              │
│                                               │
│ 3. 生成唯一 req_id（如 xyz789）               │
│ 4. 记录：                                      │
│    plan_requests[req_id] = {                  │
│      from: "alice", plan: "批量更新配置...",   │
│      status: "pending"                        │
│    }                                           │
│                                               │
│ 5. 发消息 → lead.jsonl                        │
│    type: plan_approval_response               │
│    { req_id: "xyz789", plan: "批量更新配置..." }│
│                    │                          │
└────────────────────┼───────────────────────────┘
                     │
                     ▼
┌─────────── Lead（领导） ───────────┐
│                                     │
│ 6. agent_loop 读取收件箱            │
│ 7. 收到 plan_approval_response      │
│    → 解析 plan 内容 + req_id        │
│                                     │
│ 8. 用户："审批 alice 的计划"        │
│ 9. LLM → 调用 plan_approval 工具    │
│    输入：req_id + approve: true/false + feedback │
│                                     │
│ 10. 按 req_id 匹配请求：            │
│     plan_requests[req_id].status    │
│     → approved / rejected           │
│                                     │
│ 11. 发消息 → alice.jsonl            │
│    type: plan_approval_response     │
│    { req_id: "xyz789", approve: true, feedback: "批准" } │
│                    │                │
└────────────────────┼─────────────────┘
                     │
                     ▼
┌────────── Teammate（alice） ──────────┐
│                                         │
│ 12. _teammate_loop 读取收件箱           │
│ 13. 解析审批结果：approve = true/false  │
│                                         │
│ 14. 若批准 → 执行计划（如批量修改文件） │
│     若拒绝 → 终止操作 / 调整计划后重新提交 │
│                                         │
│ 15. 任务执行完毕 → 状态切为 idle        │
│                                         │
└─────────────────────────────────────────┘


都使用 **request_id** 追踪请求状态。
基于 s09 的消息系统扩展。
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

SYSTEM = f"You are a team lead at {WORKDIR}. Manage teammates with shutdown and plan approval protocols."

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

# -- TeammateManager with shutdown + plan approval --

class TeammateManager:
    """TeammateManager: manage persistent named agents with config.json."""
    
    #初始化：加载或创建团队配置文件，启动线程池
    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.dir.mkdir(parents=True, exist_ok=True) # 确保团队目录存在
        self.config_path = self.dir / "config.json"
        self.config = self._load_config() # 加载团队配置
        self.threads = {} # name -> Thread 线程池，存储每个队员的线程

    # 加载团队配置文件，若不存在则创建默认配置    
    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"team_name": "default", "members": []}

    # 保存团队配置文件
    def _save_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"team_name": "default", "members": []}

    # 查找成员信息，返回成员字典
    def _find_member(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name:
                return m
        return None
    
    # 创建队员：添加成员到配置，启动线程运行智能体循环
    def spawn(self, name: str, role: str,prompt: str) -> str:
        member = self._find_member(name)
        if member:
            if member["status"] not in ["idle", "shutdown"]:
                return f"Error: Member {name} already exists with status {member['status']}"
            member["role"] = role
            member["status"] = "working"
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()
        thread = threading.Thread(
            target=self._teammate_loop, 
            args=(name, role, prompt),
            daemon=True
        )

        self.threads[name] = thread
        thread.start()
        return f"Spawned teammate {name} with role {role}"
    
    # # 队员循环：每个队员的智能体循环，读取消息，调用 LLM，执行工具，发消息
    def _teammate_loop(self,name:str,role:str,prompt:str):
        sys_prompt=(
            f"You are '{name}', role: {role}, at {WORKDIR}. "
            f"Submit plans via plan_approval before major work. "
            f"Respond to shutdown_request with shutdown_response."
        )

        messages = [{"role":"user","content":"prompt"}]
        tools = self._teammate_tools()
        should_exit = False

        for _ in range(50):
            inbox = BUS.read_inbox(name)
            for msg in inbox:
                messages.append({"role":"user","content":json.dumps(msg)})
            if should_exit:
                break
            try:
                response = client.messages.create(
                    model=MODEL,
                    system = sys_prompt,
                    messages = messages,
                    tools = tools,
                    max_tokens = 8000,
                )
            except Exception:
                break
            messages.append({"role":"assistant","content":response.content})
            if response.stop_reason != "tool_use":
                break
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = self._exec(name, block.name, block.input)
                    print(f"  [{name}] {block.name}: {str(output)[:120]}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output),
                    })
                    if block.name == "shutdown_response" and block.input.get("approve"):
                        should_exit = True
            messages.append({"role": "user", "content": results})
        member = self._find_member(name)
        if member:
            member["status"] = "shutdown" if should_exit else "idle"
            self._save_config()
            
    # 定义执行工具的函数，包含 send_message 工具，处理异常
    def _exec(self,sender: str, tool_name: str, args: dict) -> str:
        """Execute a tool with the given name and input."""
        if tool_name == "bash":
            return run_bash(args["command"])
        elif tool_name == "read_file":
            return run_read(args["path"])
        elif tool_name == "write_file":
            return run_write(args["path"], args["content"])
        elif tool_name == "edit_file":
            return run_edit(args["path"], args["old_text"], args["new_text"])
        elif tool_name == "send_message":
            return BUS.send(sender, args["to"], args["content"], args.get("msg_type", "message"))
        elif tool_name == "read_inbox":
            return json.dumps(BUS.read_inbox(sender), ensure_ascii=False, indent=2)
        if tool_name == "shutdown_response":
            req_id = args["request_id"]
            approve = args["approve"]
            with _tracker_lock:
                if req_id in shutdown_requests:
                    shutdown_requests[req_id]["status"] = "approved" if approve else "rejected"
            BUS.send(
                sender, "lead", args.get("reason", ""),
                "shutdown_response", {"request_id": req_id, "approve": approve},
            )
            return f"Shutdown {'approved' if approve else 'rejected'}"
        if tool_name == "plan_approval":
            plan_text = args.get("plan", "")
            req_id = str(uuid.uuid4())[:8]
            with _tracker_lock:
                plan_requests[req_id] = {"from": sender, "plan": plan_text, "status": "pending"}
            BUS.send(
                sender, "lead", plan_text, "plan_approval_response",
                {"request_id": req_id, "plan": plan_text},
            )
            return f"Plan submitted (request_id={req_id}). Waiting for lead approval."
        return f"Unknown tool: {tool_name}"
    
     # 定义工具列表，包含 send_message 和 read_inbox 工具
    def _teammate_tools(self) -> list:
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
            {"name": "shutdown_response", "description": "Respond to a shutdown request. Approve to shut down, reject to keep working.",
             "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["request_id", "approve"]}},
            {"name": "plan_approval", "description": "Submit a plan for lead approval. Provide plan text.",
             "input_schema": {"type": "object", "properties": {"plan": {"type": "string"}}, "required": ["plan"]}},
        ]
    # 列出所有队员的状态信息，供调试使用
    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)
    # 列出所有队员的名字，供工具使用
    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


TEAM = TeammateManager(TEAM_DIR) # 实例化团队管理器，供主程序使用


# -- Base tool implementations (these base tools are unchanged from s02) --
# 安全路径解析函数，确保路径在工作目录内，防止越界访问
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


# 执行 bash 命令的函数，检查危险命令，执行并捕获输出和错误，处理超时和编码问题
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, encoding='gbk', timeout=120
                           
                           )
        stdout = r.stdout or ""
        stderr = r.stderr or ""
        out = (stdout + stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except UnicodeDecodeError:
        return "Error: Encoding issue with command output"

# 读取文件的函数，使用安全路径解析，读取文本内容，支持行数限制，处理异常
def run_read(path: str, limit: int = None) -> str:
    try:
        text = safe_path(path).read_text(encoding="utf-8")
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"
    

# 写入文件的函数，使用安全路径解析，创建父目录，写入文本内容，处理异常
def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

# 编辑文件的函数，使用安全路径解析，读取现有内容，替换指定文本，写回文件，处理异常
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

# -- Lead-specific protocol handlers --
# 处理 shutdown_request 协议，生成唯一请求ID，发送请求，返回状态信息
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    with _tracker_lock:
        shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send(
        "lead", teammate, "Please shut down gracefully.",
        "shutdown_request", {"request_id": req_id},
    )
    return f"Shutdown request {req_id} sent to '{teammate}' (status: pending)"

# 处理 plan_approval 协议，更新状态，发送响应，返回状态信息
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

# 检查 shutdown_request 协议状态，返回 JSON 字�式
def _check_shutdown_status(request_id: str) -> str:
    with _tracker_lock:
        return json.dumps(shutdown_requests.get(request_id, {"error": "not found"}))


# -- Lead tool dispatch (12 tools) --
TOOL_HANDLERS = {
    "bash":            lambda **kw: run_bash(kw["command"]),
    "read_file":       lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file":      lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":       lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "spawn_teammate":  lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "list_teammates":  lambda **kw: TEAM.list_all(),
    "send_message":    lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":      lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2),
    "broadcast":       lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request":  lambda **kw: handle_shutdown_request(kw["teammate"]),
    "shutdown_response": lambda **kw: _check_shutdown_status(kw.get("request_id", "")),
    "plan_approval":     lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
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
    {"name": "spawn_teammate", "description": "Spawn a persistent teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send a message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down gracefully. Returns a request_id for tracking.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "shutdown_response", "description": "Check the status of a shutdown request by request_id.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}}, "required": ["request_id"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan. Provide request_id + approve + optional feedback.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
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
            query = input("\033[36ms10 >> \033[0m")
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
        history.append({"role": "user", "content": query})
        agent_loop(history)
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()