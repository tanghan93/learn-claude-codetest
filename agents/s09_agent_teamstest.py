#!/usr/bin/env python3
# Harness: team mailboxes -- multiple models, coordinated through files.
"""
s09_agent_teams.py - Agent Teams

Persistent named agents with file-based JSONL inboxes. Each teammate runs
its own agent loop in a separate thread. Communication via append-only inboxes.

    Subagent (s04):  spawn -> execute -> return summary -> destroyed
    Teammate (s09):  spawn -> work -> idle -> work -> ... -> shutdown

    .team/config.json                   .team/inbox/
    +----------------------------+      +------------------+
    | {"team_name": "default",   |      | alice.jsonl      |
    |  "members": [              |      | bob.jsonl        |
    |    {"name":"alice",        |      | lead.jsonl       |
    |     "role":"coder",        |      +------------------+
    |     "status":"idle"}       |
    |  ]}                        |      send_message("alice", "fix bug"):
    +----------------------------+        open("alice.jsonl", "a").write(msg)

                                        read_inbox("alice"):
    spawn_teammate("alice","coder",...)   msgs = [json.loads(l) for l in ...]
         |                                open("alice.jsonl", "w").close()
         v                                return msgs  # drain
    Thread: alice             Thread: bob
    +------------------+      +------------------+
    | agent_loop       |      | agent_loop       |
    | status: working  |      | status: idle     |
    | ... runs tools   |      | ... waits ...    |
    | status -> idle   |      |                  |
    +------------------+      +------------------+

    5 message types (all declared, not all handled here):
    +-------------------------+-----------------------------------+
    | message                 | Normal text message               |
    | broadcast               | Sent to all teammates             |
    | shutdown_request        | Request graceful shutdown (s10)   |
    | shutdown_response       | Approve/reject shutdown (s10)     |
    | plan_approval_response  | Approve/reject plan (s10)         |
    +-------------------------+-----------------------------------+

Key insight: "Teammates that can talk to each other."

s09_agent_teams.py - Agent Teams

持久化命名智能体，基于文件收件箱实现多 AI 协作。
每个队友在独立线程运行自己的循环。
通过“只追加收件箱”通信。

子代理（s04）：创建 → 执行 → 返回 → 销毁
队友（s09）：创建 → 工作 → 空闲 → 工作 → 关机

消息存在 .team/inbox/ 下
发送消息 = 往文件追加一行
读取消息 = 读取并清空文件

核心：AI 队友可以互相聊天、协作。

┌──────────────────────────────────────────────────────────────┐
│                     终端用户 / 主 Lead 智能体                  │
│  输入指令：spawn_teammate / send_message / broadcast          │
└───────────────┬──────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────┐
│                TeammateManager 团队管理器                     │
│  1. 维护 .team/config.json 保存所有队员名字/角色/状态        │
│  2. 为每个队员 启动独立守护线程 threading.Thread             │
│  3. 每个线程内部跑专属 _teammate_loop 智能体循环              │
└───────────────┬──────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────┐
│                   MessageBus 消息总线（核心通信层）           │
│  存储位置：.team/inbox/xxx.jsonl                              │
│  通信规则：                                                   │
│  ✅ 发消息：追加写入 目标队员.jsonl                           │
│  ✅ 收消息：读取整行 → 解析JSON → 清空文件                    │
│  ✅ 支持：私聊 / 全员广播 / 各类系统消息类型                   │
└───────────────┬──────────────────────────────────────────────┘
                │
                ├─────────────────────┬─────────────────────┐
                ▼                     ▼                     ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ 队员A(alice)线程 │      │ 队员B(bob)线程   │      │ 队员C(xxx)线程  │
│ _teammate_loop   │      │ _teammate_loop   │      │ _teammate_loop   │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────────────────────────────────────────────────┐
│ 单个AI队员标准工作循环（每个人都一模一样）                    │
│  1. 每轮先调用 BUS.read_inbox() 读取自己收件箱                │
│  2. 把收到的消息并入对话上下文 messages                      │
│  3. 调用 Claude LLM 思考决策                                  │
│  4. 可调用工具：bash / 读写文件 / edit / send_message       │
│  5. 可主动给其他队员发消息协作                                │
│  6. 最多循环50轮任务结束 → 状态切为 idle 空闲                │
└──────────────────────────────────────────────────────────────┘
"""

from importlib.resources import read_text
import json
import os
import subprocess
import threading   # 多线程：让多个 AI 同时运行
import time
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

SYSTEM = f"You are a team lead at {WORKDIR}. Spawn teammates and communicate via inboxes."

# 声明所有消息类型，供后续实现使用
VALID_MSG_TYPES = {
    "message",  # 普通文本消息
    "broadcast", # 全员广播消息
    "shutdown_request", # 关机请求消息
    "shutdown_response", # 关机响应消息
    "plan_approval_response", # 计划审批响应消息
}

# -- MessageBus: JSONL inbox per teammate --
class MessageBus:
    """MessageBus: file-based JSONL inbox for each teammate."""
    
    #初始化：确保团队目录和收件箱目录存在
    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True) # 确保收件箱目录存在
    
    # 发送消息：写给对应名字的 jsonl 文件
    def send(self,sender: str, to: str,content: str, msg_type: str="message", extra: dict=None) -> str:
        """Send a message to a teammate's inbox."""
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid type '{msg_type}'. Valid types: {VALID_MSG_TYPES}"
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time()

        }
        if extra:
            msg.update(extra)
        inbox_path = self.dir / f"{to}.jsonl"
        with open(inbox_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"Sent {msg_type} to {to}"
    
    # 读取消息：读对应名字的 jsonl 文件，返回消息列表，并清空文件
    def read_inbox(self, name: str) -> list:
        """Read and clear messages from a teammate's inbox."""
        inbox_path = self.dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return []
        messages = []
        for line in inbox_path,read_text(encoding="utf-8").strip().splitlines():
            if line:
                messages.append(json.loads(line))
        inbox_path.write_text("", encoding="utf-8") # 清空收件箱
        return messages
    
    # 广播消息：发给所有队员的 jsonl 文件
    def broadcast(self, sender: str, content: str, teammates: list) -> str:
        count = 0
        for name in teammates:
            if name != sender: # 不发给自己
                self.send(sender, name, content)
                count += 1
        return f"Broadcasted to {count} teammates"
    

BUS = MessageBus(INBOX_DIR) # 实例化消息总线，供工具处理器使用

# -- TeammateManager: persistent named agents with config.json --
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
    
    # 队员循环：每个队员的智能体循环，读取消息，调用 LLM，执行工具，发消息
    def _teammate_loop(self, name: str, role: str, prompt: str):
        """设置定制化的系统提示，包含队员角色和团队信息，进入循环：读消息 → 思考 → 执行工具 → 发消息"""

        sys_prompt = (
            f"You are {name}, a {role} in team {self.config['team_name']} at {WORKDIR}.\n"
            f"Use send_message(to, content) to talk to teammates. Complete the task as instructed.\n"
        )
        messages = [{"role": "system", "content": prompt}]
        tools = self._teammate_tools() # 获取工具列表，包含 send_message 工具
        for _ in range(50): # 最多循环50轮
            inbox_msgs = BUS.read_inbox(name) # 读自己的收件箱
            if inbox_msgs:
                messages.append({"role": "user", "content": f"Received messages: {json.dumps(inbox_msgs, ensure_ascii=False)}"})
            try:
                response = client.messages.create(
                    model=MODEL, system=sys_prompt, messages=messages,
                    tools=tools, max_tokens=8000,
                )
            except Exception as e:
                break
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "tool_use":
                break

            # 处理工具调用结果，发消息给其他队员        
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = self._exec(name, block.name, block.input) # 执行工具
                    print(f"[{name}] {block.name} : {str(output)[:200]}") # 打印工具调用结果
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id, "content": str(output)
                    }) # 把工具调用结果加入结果列表，供后续发消息使用

            messages.append({"role": "user", "content": results}) # 把工具调用结果加入对话上下文，供下一轮思考使用
        member = self._find_member(name)
        if member and member["status"] != "shutdown":
            member["status"] = "idle" # 循环结束后状态改为 idle 空闲
            self._save_config()

    # 定义执行工具的函数，包含 send_message 工具，处理异常
    def _exec(self, sender: str, tool_name: str, args: dict) -> str:
        # these base tools are unchanged from s02
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
        return f"Error: Unknown tool {tool_name}"
    
    # 定义工具列表，包含 send_message 和 read_inbox 工具
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
        ]
    
    # 列出所有队员的状态信息，供调试使用
    def list_all(self) -> list:
        if not self.config["members"]:
            return "No teammates yet."
        lines = [f"Team {self.config['team_name']} members:"]
        for member in self.config["members"]:
            lines.append(f"  - {member['name']}: {member['status']}")
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
    
# -- Lead tool dispatch (9 tools) --
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
    {"name": "spawn_teammate", "description": "Spawn a persistent teammate that runs in its own thread.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates with name, role, status.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate's inbox.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send a message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
]


#主循环：每轮调用 LLM 前，先检查所有队员的通知队列，把完成的任务结果注入到消息中，让模型知道
def agent_loop(messages: list):
    while True:
        inbox_msgs = BUS.read_inbox("lead") # 读 lead 的收件箱
        if inbox_msgs:
            messages.append({
                "role": "user", 
                "content": f"Received messages: {json.dumps(inbox_msgs, ensure_ascii=False,indent=2 )}"
                })
            
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    output = handler(**block.input) if handler else f"Error: No handler for tool {block.name}"
                except Exception as e:
                    output = f"Error executing tool {block.name}: {e}"
                print(f"[lead] {block.name} : {str(output)[:200]}") # 打印工具调用结果
                print(str(output)[:200]) # 打印工具调用结果
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(output)}
                )
        messages.append({"role": "user", "content": results}) # 把工具调用结果加入对话上下文，供下一轮思考使用

# 主程序：初始化消息列表，调用主循环
if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms09 >> \033[0m")
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
