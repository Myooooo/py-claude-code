"""Py Claude Code - Python版 Claude Code 编程助手.

一个兼容 OpenAI Chat Completions API 的编程助手，支持多轮对话、工具调用和流式输出。
"""

__version__ = "0.1.0"
__author__ = "Py Claude Code"

from .config import Config, load_config
from .chat import ChatManager, ChatSession, ConversationContext
from .llm import OpenAIClient, Message, LLMResponse
from .tools.base import BaseTool, ToolResult, tool_registry
from .ui import UI, console

__all__ = [
    "__version__",
    "Config",
    "load_config",
    "ChatManager",
    "ChatSession",
    "ConversationContext",
    "OpenAIClient",
    "Message",
    "LLMResponse",
    "BaseTool",
    "ToolResult",
    "tool_registry",
    "UI",
    "console",
]
