"""工具模块.

提供各种工具供AI助手使用：
- file: 文件操作工具（读取、写入、编辑）
- bash: Bash命令执行工具
- search: 搜索工具（glob、grep）
- todo: 待办事项管理工具
- web: Web工具（网页获取、搜索）
- base: 工具基类和注册表
"""

from .base import BaseTool, ToolParameters, ToolResult, ToolRegistry, tool_registry
from .file import FileReadTool, FileWriteTool, FileEditTool, ViewTool
from .bash import BashTool
from .search import GlobTool, GrepTool

# 导入以注册工具
from . import todo
from . import web
from . import tasks

__all__ = [
    # 基类
    "BaseTool",
    "ToolParameters",
    "ToolResult",
    "ToolRegistry",
    "tool_registry",
    # 文件工具
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "ViewTool",
    # Bash工具
    "BashTool",
    # 搜索工具
    "GlobTool",
    "GrepTool",
    # 待办工具
    "todo",
    # Web工具
    "web",
    # 任务工具
    "tasks",
]
