"""
配置文件：API keys 和基础设置
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic"

# 模型配置
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"
MODEL_DEEPSEEK_CHAT = "deepseek-chat"

# 默认模型
DEFAULT_MODEL = MODEL_DEEPSEEK_REASONER
