#!/usr/bin/env python3
# Harness: compression -- clean memory for infinite sessions.
"""
s06_context_compact.py - Compact

Three-layer compression pipeline so the agent can work forever:

    Every turn:
    +------------------+
    | Tool call result |
    +------------------+
            |
            v
    [Layer 1: micro_compact]        (silent, every turn)
      Replace non-read_file tool_result content older than last 3
      with "[Previous: used {tool_name}]"
            |
            v
    [Check: tokens > 50000?]
       |               |
       no              yes
       |               |
       v               v
    continue    [Layer 2: auto_compact]
                  Save full transcript to .transcripts/
                  Ask LLM to summarize conversation.
                  Replace all messages with [summary].
                        |
                        v
                [Layer 3: compact tool]
                  Model calls compact -> immediate summarization.
                  Same as auto, triggered manually.

Key insight: "The agent can forget strategically and keep working forever."
s06_context_compact.py - Compact

三层压缩管道，让智能体可以永久工作：
每一轮：
工具结果 → 微压缩（清理旧结果）→ 判断 Token 是否超限
→ 不超限：继续
→ 超限：自动总结 + 清理上下文

关键思想：智能体可以策略性遗忘，然后继续工作。
"""


import json
import os
import subprocess
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


SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks."

THRESHOLD = 50000  # token 数超过5 万 Token 这个值就触发自动压缩
TRANSCRIPTS_DIR = WORKDIR / ".transcripts"  # 对话存档目录
KEEP_RECENT = 3  # micro_compact 保留每个工具调用后最近的 KEEP_REC 条消息
PRESERVE_RESULT_TOOLS = {"read_file"}  # micro_compact 保留 read_file工具调用的结果内容，其他工具调用结果会被替换为占位文本

#定义估算token函数
def estimate_tokens(messages):
    # 简单的 token 估算函数，每条消息按字数除以 4 来估算 token 数
    return len(str(messages)) // 4


# -- Layer 1: micro_compact - replace old tool results with placeholders --
def micro_compact(messages)-> list:
    # Collect (msg_index, part_index, tool_result_dict) for all tool_result entries
    # 收集所有 tool_result
    tool_results = []
    
    for msg_idex,msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg["content"], list):
            for part_index, part in enumerate(msg["content"]):
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append((msg_idex, part_index, part))
     # 不超过 3 条就不清理
    if len(tool_results) <= KEEP_RECENT:
        return messages  # 不需要压缩，直接返回原消息列表
     # 找到每个 tool_result 对应的工具名
     # Find tool_name for each result by matching tool_use_id in prior assistant messages
    tool_name_map = {}
    for msg in messages:
        if msg["role"] == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_name_map[block.id] = block.name
    
    # Clear old tool results (keep last KEEP_RECENT).Preserve read_file outputs because
    # they are reference material; compacting them forces the agent to re-read files.
    # 清理旧的工具结果（只保留最近 3 条）
    to_clear = tool_results[:-KEEP_RECENT]  # 需要清理的工具调用结果
    for _,_, result in to_clear:
        # 短内容不清理
        if not isinstance(result.get("content"), str) or len(result["content"]) <= 100:
            continue
        tool_id = result.get("tool_use_id", "")
        tool_name = tool_name_map.get(tool_id, "unknown")
        # read_file 不压缩
        if tool_name in PRESERVE_RESULT_TOOLS:
            continue
        # 替换成简化文字
        result["content"] = f"[Previous: used {tool_name}]"
    return messages


# -- Layer 2: auto_compact - save transcript, summarize, replace messages --
def auto_compact(messages)-> list:
    # Save full transcript to disk保存完整对话到文件
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    transcript_path = TRANSCRIPTS_DIR / f"transcript_{int(time.time())}.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False,default=str) + "\n")

    print(f"[Transcript saved to {transcript_path}]")
    # Ask LLM to summarize conversation
    conversation_text = json.dumps(messages, ensure_ascii=False, default=str)[-80000:]
    response = client.messages.create(
        model=MODEL, 
        messages=[{"role": "user", "content": 
                   "Summarize this conversation for continuity. Include: "
                    "1) What was accomplished, 2) Current state, 3) Key decisions made. "
                    "Be concise but preserve critical details.\n\n" + conversation_text}],
        max_tokens=2000,
                   
    )
    summary = next((block.text for block in response.content if hasattr(block, "text")), "")
    if not summary:
        summary = "No summary generated."
    # Replace all messages with compressed summary   用总结替换所有历史
    return [
        {"role": "user", "content": f"[Conversation compressed. Transcript: {transcript_path}]\n\n{summary}"},
    ]


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
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "compact":    lambda **kw: "Manual compression requested.",
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "compact", "description": "Trigger manual conversation compression.",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string", "description": "What to preserve in the summary"}}}},
]

def agent_loop(messages: list):
    while True:
        # Layer 1: micro_compact before each LLM call 第一层：微压缩
        micro_compact(messages)
        # Layer 2: auto_compact if token estimate exceeds threshold 第二层：超过 Token 自动压缩
        if estimate_tokens(messages) > THRESHOLD:
            print("[auto_compact triggered]")
            messages[:] = auto_compact(messages)
       # 调用 AI
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        # 执行工具
        results = []
        manual_compact = False
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "compact":
                    manual_compact = True  # 第三层：手动压缩
                    output = "Compressing..."
                else:
                    handler = TOOL_HANDLERS.get(block.name)
                    try:
                        output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                    except Exception as e:
                        output = f"Error: {e}"
                print(f"> {block.name}:")
                print(str(output)[:200])
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        messages.append({"role": "user", "content": results})
        # Layer 3: manual compact triggered by the compact tool 如果 AI 调用了 compact 工具 → 立刻总结
        if manual_compact:
            print("[manual compact]")
            messages[:] = auto_compact(messages)
            return
        
if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms06 >> \033[0m")
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
