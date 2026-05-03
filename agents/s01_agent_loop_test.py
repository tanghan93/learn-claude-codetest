#!/usr/bin/env python3
# Harness: the loop -- the model's first connection to the real world.
"""
s01_agent_loop.py - The Agent Loop

The entire secret of an AI coding agent in one pattern:

    while stop_reason == "tool_use":
        response = LLM(messages, tools)
        execute tools
        append results

    +----------+      +-------+      +---------+
    |   User   | ---> |  LLM  | ---> |  Tool   |
    |  prompt  |      |       |      | execute |
    +----------+      +---+---+      +----+----+
                          ^               |
                          |   tool_result |
                          +---------------+
                          (loop continues)

This is the core loop: feed tool results back to the model
until the model decides to stop. Production agents layer
policy, hooks, and lifecycle controls on top.
"""

import os
import subprocess
import json

from dotenv import load_dotenv
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEFAULT_MODEL

load_dotenv(override=True)

SYSTEM = "You are a helpful AI assistant with access to tools. Use them to solve the user's request."

# Set up the OpenAI client using the base URL and API key from environment variables
client = OpenAI(base_url="https://api.deepseek.com/beta", api_key=DEEPSEEK_API_KEY)
MODEL = DEFAULT_MODEL
#* deepseek-chat 和 deepseek-reasoner 对应模型版本不变，
#为 DeepSeek-V3.2 (128K 上下文长度)，与 APP/WEB 版不同。
#deepseek-chat 对应 DeepSeek-V3.2 的非思考模式，
#deepseek-reasoner 对应 DeepSeek-V3.2 的思考模式。

#工具定义，当前仅定义了一个 bash 工具，用于执行 shell 命令。

TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                },
            },
            "required": ["command"],
        }
    }
}]
# run_bash 函数：执行 shell 命令
# 说明：
# 1. 接收一个字符串参数 command，代表要执行的 shell 命令。
# 2. 检查命令是否包含危险操作（如删除根目录、执行系统命令等），如果包含则返回错误提示。
# 3. 尝试执行命令，设置超时为 120 秒。
# 4. 如果命令执行成功，返回标准输出或 "(no output)"。
# 5. 如果命令执行超时，返回超时提示。
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    print(f"Running command: {command}")
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked."
    try:
        r = subprocess.run(
            command, shell=True, cwd=os.getcwd(),
            capture_output=True, text=True, timeout=120,
            encoding="gbk",
            errors="replace"

        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out(120s)."
    

# 主循环：接收用户提问，调用大模型，若模型要求执行工具则循环执行，直到模型给出最终回答为止
def agent_loop(messages):
    print("Entering agent loop with messages:")
    print("history:", messages)
    print("Starting agent loop...")
    while True:
        # OpenAI 格式不支持顶层的 system 参数，需要将 SYSTEM 作为第一条消息传入
        # 但我们已经在主程序初始化 history 时放入了 system 消息，所以这里直接传 messages 即可
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        message = response.choices[0].message
        print("Model response:", message)  # 打印模型的原始响应，包含工具调用信息
        # 将助手的回复添加到消息记录中
        messages.append(message)

        # 如果模型没有调用工具，则直接返回，结束本轮对话
        if not message.tool_calls:
            print("No tool calls, returning final response.")
            return

        # 如果调用了工具，则遍历并执行
        for tool_call in message.tool_calls:
            if tool_call.function.name == "bash":
                args = json.loads(tool_call.function.arguments)
                output = run_bash(args["command"])
                # 将工具执行的结果添加回消息记录，role 为 tool
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": output,
                })

# 主程序：处理用户输入并与模型交互
# 说明：当脚本被直接运行时，进入交互式循环。
# 1. 初始化一个空列表 history 用于保存对话历史。
# 2. 循环读取用户输入（带青色提示符 "s01 >> "）。
# 3. 用户输入 q/exit/空行 时退出。
# 4. 将用户输入追加到 history，调用 agent_loop 让模型处理。
# 5. 取出模型返回的最后一条消息，打印其 content 字段。
# 6. 遇到 EOF (Ctrl-D) 或键盘中断 (Ctrl-C) 时优雅退出。
if __name__ == "__main__":
    history = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        
        agent_loop(history)
        last_msg = history[-1]
        # last_msg 在 agent_loop 中被追加为 openai.types.chat.chat_completion_message.ChatCompletionMessage 对象
        if hasattr(last_msg, 'content') and last_msg.content:
            print(last_msg.content)
        print()