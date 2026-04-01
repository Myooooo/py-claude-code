"""工具基类定义."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar
from pydantic import BaseModel, Field


class ToolParameters(BaseModel):
    """工具参数基类."""

    class Config:
        extra = "forbid"


class ToolResult(BaseModel):
    """工具执行结果."""

    success: bool = Field(..., description="是否成功")
    content: str = Field(default="", description="结果内容")
    error: str | None = Field(default=None, description="错误信息")
    data: dict[str, Any] = Field(default_factory=dict, description="额外数据")

    @classmethod
    def ok(cls, content: str, **data: Any) -> "ToolResult":
        """创建成功结果."""
        return cls(success=True, content=content, data=data)

    @classmethod
    def error(cls, message: str, **data: Any) -> "ToolResult":
        """创建错误结果."""
        return cls(success=False, error=message, data=data)


TParams = TypeVar("TParams", bound=ToolParameters)


class BaseTool(ABC, BaseModel):
    """工具基类."""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")

    class Config:
        arbitrary_types_allowed = True

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具."""
        pass

    @abstractmethod
    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数JSON Schema."""
        pass

    def to_openai_function(self) -> dict[str, Any]:
        """转换为OpenAI Function Calling格式."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }


class ToolRegistry:
    """工具注册表."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """获取工具."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """列出所有工具."""
        return list(self._tools.values())

    def get_openai_functions(self) -> list[dict[str, Any]]:
        """获取所有工具的OpenAI Function格式."""
        return [tool.to_openai_function() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        """检查工具是否存在."""
        return name in self._tools


# 全局工具注册表
tool_registry = ToolRegistry()
