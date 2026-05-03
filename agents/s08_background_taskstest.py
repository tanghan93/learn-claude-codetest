#!/usr/bin/env python3
# Harness: background execution -- the model thinks while the harness waits.
"""
s08_background_tasks.py - Background Tasks

Run commands in background threads. A notification queue is drained
before each LLM call to deliver results.

    Main thread                Background thread
    +-----------------+        +-----------------+
    | agent loop      |        | task executes   |
    | ...             |        | ...             |
    | [LLM call] <---+------- | enqueue(result) |
    |  ^drain queue   |        +-----------------+
    +-----------------+

    Timeline:
    Agent ----[spawn A]----[spawn B]----[other work]----
                 |              |
                 v              v
              [A runs]      [B runs]        (parallel)
                 |              |
                 +-- notification queue --> [results injected]

Key insight: "Fire and forget -- the agent doesn't block while the command runs."

s08_background_tasks.py - Background Tasks

后台线程运行命令。
每次调用 LLM 前，先把通知队列里的结果取出来交给 AI。

主线程：AI 循环
后台线程：执行任务，完成后放入队列

时间线：
AI 发起任务A → 发起任务B → 继续做别的
        |             |
        v             v
      任务A运行      任务B运行 （并行）
        |             |
        --------→ 通知队列 → 下次 LLM 时交给 AI

关键思想：发起后不用管，AI 不会被卡住！
"""

import os
import subprocess   # 执行命令
import threading    # 多线程（后台运行）
import uuid         # 生成唯一任务 ID
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

SYSTEM = f"You are a coding agent at {WORKDIR}. Use background_run for long-running commands."

# -- BackgroundManager: threaded execution + notification queue --
class BackgroundManager:
    """Manage background tasks with a notification queue.

    Tasks are run in separate threads. When a task completes, its result
    is put into a thread-safe queue. The main agent loop checks this
    queue before each LLM call and injects any results into the messages.
    """
    
    #初始化：创建一个空的通知队列
    def __init__(self) -> None:
        self.tasks = {} # task_id -> {status, result,command} 任务ID → 任务信息
        self._notification_queue = [] # completed task results 存储完成任务的结果的通知列表
        self._lock = threading.Lock() # 线程锁，保护共享数据结构 保护 self.tasks 和 self._notifications 的线程安全
    
    #后台运行命令的函数，接受命令字符串，生成唯一任务 ID，启动线程执行命令，立即返回任务 ID
    def run(self, command: str) -> str:
        """Start a background thread, return task_id immediately."""

        task_id = str(uuid.uuid4())[:8] # 生成一个8位的短的唯一任务 ID
        self.tasks[task_id] = {"status": "running", "result": None, "command": command} # 在任务字典中记录这个任务的状态和命令
        thread = threading.Thread(
            target=self._execute, args=(task_id, command), daemon=True # 创建一个后台线程，目标函数是 _execute，传入任务 ID 和命令
        )
        thread.start() # 启动线程，开始执行命令
        return f"Background task {task_id} started for command: {command}" # 返回一个字符串，告诉调用者任务已经开始，并提供任务 ID 和命令信息

    def _execute(self, task_id: str, command: str) -> None:
        """Thread target: run subprocess, capture output, push to queue."""
        try:
            # 执行命令
            r = subprocess.run(
                command, shell=True, cwd=WORKDIR,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300
            )
            output = (r.stdout + r.stderr).strip()[:50000] # 获取命令的标准输出和标准错误，合并并去除首尾空白
            status = "completed" # 任务状态改为完成
        except subprocess.TimeoutExpired:
            output = "Error: Timeout (300s)" # 超时错误信息
            status = "timeout" # 任务状态改为超时
        
        except Exception as e:
            output = f"Error: {e}" # 其他异常错误信息
            status = "error" # 任务状态改为错误
        
        # 更新任务状态
        self.tasks[task_id]["status"] = status
        self.tasks[task_id]["result"] = output or "(no output)"

        # 放入通知队列
        with self._lock: # 获取锁，确保线程安全地访问通知队列
            self._notification_queue.append({
                "task_id": task_id,
                "status": status,
                "command":command[:80],
                "result": (output or "(no output)")[:500]
            }) # 将任务结果放入通知列表中
    

    def check(self, task_id: str=None) -> str:
        """Check status of one task or list all."""
       
        if task_id:
            #返回单个任务状态
            task = self.tasks.get(task_id)
            if not task:
                return f"Error: Unknown task {task_id}"
            return f"[{task['status']}] {task['command'][:60]} \n {task.get('result')or'(running)'}"
        lines = []
        for tid, t in self.tasks.items():
            lines.append(f"{tid}: [{t['status']}] {t['command'][:60]}")
        return "\n".join(lines) if lines else  "No background tasks."

    def drain_notifications(self) -> list:      
        """Return and clear all pending completion notifications."""        
        with self._lock: # 获取锁，确保线程安全地访问通知队列
            notifs = list(self._notification_queue) # 列出所有当前的通知
            self._notification_queue.clear() # 清空原始通知列表
        return notifs # 返回复制的通知列表

# 实例化背景任务管理器，供工具处理器使用
BG = BackgroundManager()

# -- Tool implementations --
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

TOOL_HANDLERS = {
    "bash":             lambda **kw: run_bash(kw["command"]),
    "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "background_run":   lambda **kw: BG.run(kw["command"]),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command (blocking).",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "background_run", "description": "Run command in background thread. Returns task_id immediately.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "check_background", "description": "Check background task status. Omit task_id to list all.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
]


# 主循环：接收用户提问，调用大模型，若模型要求执行工具则循环执行，直到模型给出最终回答为止
def agent_loop(messages: list):
    while True:
        # 在每次调用 LLM 前，先检查后台任务的通知队列，把完成的任务结果注入到消息中，让模型知道
        notifs = BG.drain_notifications() # 从背景任务管理器中取出所有完成任务的通知
        if notifs and messages:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}]{n['status']}:{n['result']}" for n in notifs
            )
            messages.append({"role": "user","content": f"<background_updates>\n{notif_text}\n</background_updates>"}) # 将通知格式化成文本，添加到消息列表中，使用特殊标签 <background_updates> 包裹，供模型识别
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
                    output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    output = f"Error: {e}"
                print(f"> {block.name}:")
                print(str(output)[:200])
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms08 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()