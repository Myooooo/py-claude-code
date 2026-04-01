"""OpenAI API客户端."""

import json
from typing import Any, AsyncIterator, Literal
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)

from .config import Config
from .tools.base import tool_registry


@dataclass
class Message:
    """聊天消息."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为API格式."""
        result: dict[str, Any] = {"role": self.role}

        if self.content is not None:
            result["content"] = self.content

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.name:
            result["name"] = self.name

        return result

    @classmethod
    def system(cls, content: str) -> "Message":
        """创建系统消息."""
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        """创建用户消息."""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str | None = None) -> "Message":
        """创建助手消息."""
        return cls(role="assistant", content=content)

    @classmethod
    def tool(cls, content: str, tool_call_id: str) -> "Message":
        """创建工具消息."""
        return cls(role="tool", content=content, tool_call_id=tool_call_id)


@dataclass
class ToolCall:
    """工具调用."""

    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_api(cls, tool_call_data: ChatCompletionMessageToolCall) -> "ToolCall":
        """从API响应创建."""
        return cls(
            id=tool_call_data.id,
            name=tool_call_data.function.name,
            arguments=json.loads(tool_call_data.function.arguments),
        )


@dataclass
class LLMResponse:
    """LLM响应."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    raw_response: Any | None = None

    @property
    def has_tool_calls(self) -> bool:
        """是否有工具调用."""
        return len(self.tool_calls) > 0


class OpenAIClient:
    """OpenAI API客户端."""

    def __init__(self, config: Config | None = None):
        """初始化客户端."""
        self.config = config or Config()
        self.client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse | AsyncIterator[str]:
        """
        发送聊天请求.

        Args:
            messages: 消息列表
            tools: 可用工具列表
            stream: 是否流式输出
            temperature: 采样温度
            max_tokens: 最大token数

        Returns:
            LLMResponse 或 流式输出迭代器
        """
        # 转换消息格式
        api_messages = [msg.to_dict() for msg in messages]

        # 构建请求参数
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": stream,
        }

        # 添加工具
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        if stream:
            return self._chat_stream(params)
        else:
            return await self._chat_completion(params)

    async def _chat_completion(self, params: dict[str, Any]) -> LLMResponse:
        """非流式聊天完成."""
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                **params
            )

            choice = response.choices[0]
            message = choice.message

            # 提取工具调用
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(ToolCall.from_api(tc))

            # 提取使用量
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                usage=usage,
                raw_response=response,
            )

        except Exception as e:
            raise LLMError(f"API请求失败: {e}") from e

    async def _chat_stream(self, params: dict[str, Any]) -> AsyncIterator[str]:
        """流式聊天完成."""
        try:
            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                chunk: ChatCompletionChunk
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

        except Exception as e:
            raise LLMError(f"流式API请求失败: {e}") from e

    async def chat_with_tools(
        self,
        messages: list[Message],
        max_iterations: int = 10,
        tool_callback: callable | None = None,
        summarize_callback: callable[[str], str] | None = None,
    ) -> LLMResponse:
        """
        支持工具调用的对话.

        Args:
            messages: 消息列表
            max_iterations: 最大工具调用迭代次数
            tool_callback: 工具执行回调函数(tool_name, result) -> None

        Returns:
            最终响应
        """
        tools = tool_registry.get_openai_functions()
        current_messages = messages.copy()
        iterations = 0

        while iterations < max_iterations:
            # 发送请求
            response = await self.chat(current_messages, tools=tools)

            if isinstance(response, AsyncIterator):
                raise ValueError("流式输出不支持工具调用")

            # 如果没有工具调用，直接返回
            if not response.has_tool_calls:
                return response

            # 添加助手消息
            assistant_msg = Message.assistant()
            assistant_msg.tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in response.tool_calls
            ]
            assistant_msg.content = response.content
            current_messages.append(assistant_msg)

            # 执行工具调用
            for tool_call in response.tool_calls:
                tool = tool_registry.get(tool_call.name)
                if tool:
                    from .tools.base import ToolResult

                    result: ToolResult = await tool.execute(**tool_call.arguments)

                    # 回调通知（使用原始结果）
                    if tool_callback:
                        tool_callback(tool_call.name, result)

                    # 处理工具结果内容
                    content = result.content if result.success else f"错误: {result.error}"

                    # 应用摘要（如果启用且内容过长）
                    if summarize_callback and len(content) > 1000:
                        content = summarize_callback(content)

                    # 添加工具结果消息
                    current_messages.append(Message.tool(
                        content=content,
                        tool_call_id=tool_call.id,
                    ))
                else:
                    # 工具不存在
                    current_messages.append(Message.tool(
                        content=f"错误: 工具 '{tool_call.name}' 不存在",
                        tool_call_id=tool_call.id,
                    ))

            iterations += 1

        # 达到最大迭代次数
        return LLMResponse(
            content="（达到最大工具调用次数限制）",
            finish_reason="max_iterations",
        )

    async def simple_chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """
        简单对话接口.

        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            stream: 是否流式输出

        Returns:
            响应文本或流式迭代器
        """
        messages = []
        if system_prompt:
            messages.append(Message.system(system_prompt))
        messages.append(Message.user(prompt))

        response = await self.chat(messages, stream=stream)

        if stream:
            return response
        elif isinstance(response, LLMResponse):
            return response.content or ""
        return ""


class LLMError(Exception):
    """LLM错误."""
    pass


def create_client(config: Config | None = None) -> OpenAIClient:
    """创建LLM客户端."""
    return OpenAIClient(config)
