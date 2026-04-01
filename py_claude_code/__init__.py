"""Py Claude Code - Python版 Claude Code 编程助手.

一个兼容 OpenAI Chat Completions API 的编程助手，支持多轮对话、工具调用和流式输出。

特性:
- Token-based 上下文管理
- 智能上下文压缩
- 会话持久化存储
- 检查点系统
- 长期记忆
"""

__version__ = "0.2.0"
__author__ = "Py Claude Code"

from .config import Config, load_config
from .chat import ChatManager, ChatSession, ConversationContext, Checkpoint
from .llm import OpenAIClient, Message, LLMResponse
from .tools.base import BaseTool, ToolResult, tool_registry
from .token_manager import TokenManager, TokenMetrics
from .storage import SessionStorage
from .memory import MemoryManager
from .ui import UI, console

__all__ = [
    "__version__",
    "Config",
    "load_config",
    "ChatManager",
    "ChatSession",
    "ConversationContext",
    "Checkpoint",
    "OpenAIClient",
    "Message",
    "LLMResponse",
    "BaseTool",
    "ToolResult",
    "tool_registry",
    "TokenManager",
    "TokenMetrics",
    "SessionStorage",
    "MemoryManager",
    "UI",
    "console",
]
