"""对话管理模块."""

from typing import Any, AsyncIterator
from dataclasses import dataclass, field

from .config import Config
from .llm import Message, OpenAIClient, LLMResponse
from .tools.base import ToolResult


@dataclass
class ConversationContext:
    """对话上下文."""

    messages: list[Message] = field(default_factory=list)
    max_messages: int = 50

    def add_message(self, message: Message) -> None:
        """添加消息."""
        self.messages.append(message)
        # 限制上下文长度
        if len(self.messages) > self.max_messages:
            # 保留系统消息和最近的消息
            system_msgs = [m for m in self.messages if m.role == "system"]
            other_msgs = [m for m in self.messages if m.role != "system"]
            # 保留最近的 max_messages - len(system_msgs) 条非系统消息
            kept = other_msgs[-(self.max_messages - len(system_msgs)):]
            self.messages = system_msgs + kept

    def get_messages(self) -> list[Message]:
        """获取所有消息."""
        return self.messages.copy()

    def clear(self) -> None:
        """清空消息（保留系统消息）."""
        self.messages = [m for m in self.messages if m.role == "system"]

    def set_system_message(self, content: str) -> None:
        """设置系统消息."""
        # 移除旧的系统消息
        self.messages = [m for m in self.messages if m.role != "system"]
        # 添加新的系统消息
        self.messages.insert(0, Message.system(content))


class ChatSession:
    """聊天会话."""

    def __init__(
        self,
        config: Config | None = None,
        system_prompt: str | None = None,
    ):
        """初始化会话."""
        self.config = config or Config()
        self.client = OpenAIClient(self.config)
        self.context = ConversationContext(
            max_messages=self.config.max_context_messages
        )

        # 设置系统提示词
        if system_prompt:
            self.context.set_system_message(system_prompt)
        else:
            self.context.set_system_message(self.config.system_prompt)

        self.tool_history: list[dict[str, Any]] = []

    async def send_message(
        self,
        content: str,
        use_tools: bool = True,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """
        发送消息.

        Args:
            content: 消息内容
            use_tools: 是否使用工具
            stream: 是否流式输出

        Returns:
            响应文本或流式迭代器
        """
        # 添加用户消息
        self.context.add_message(Message.user(content))

        if use_tools:
            return await self._chat_with_tools(stream)
        else:
            return await self._simple_chat(stream)

    async def _simple_chat(self, stream: bool) -> str | AsyncIterator[str]:
        """简单对话."""
        messages = self.context.get_messages()
        response = await self.client.chat(messages, stream=stream)

        if stream:
            return self._handle_stream(response)
        else:
            if isinstance(response, LLMResponse):
                # 添加助手消息到上下文
                if response.content:
                    self.context.add_message(Message.assistant(response.content))
                return response.content or ""
            return ""

    async def _chat_with_tools(
        self,
        stream: bool
    ) -> str | AsyncIterator[str]:
        """支持工具调用的对话."""
        messages = self.context.get_messages()

        # 收集工具执行结果
        tool_results: list[tuple[str, ToolResult]] = []

        def on_tool_call(name: str, result: ToolResult) -> None:
            """工具调用回调."""
            tool_results.append((name, result))
            self.tool_history.append({
                "tool": name,
                "success": result.success,
                "content": result.content[:200] if len(result.content) > 200 else result.content,
            })

        response = await self.client.chat_with_tools(
            messages,
            max_iterations=self.config.max_tool_iterations,
            tool_callback=on_tool_call,
        )

        # 添加助手消息到上下文
        assistant_content = response.content or ""
        self.context.add_message(Message.assistant(assistant_content))

        return assistant_content

    async def _handle_stream(
        self,
        stream: AsyncIterator[str]
    ) -> AsyncIterator[str]:
        """处理流式输出."""
        content_parts = []

        async for chunk in stream:
            content_parts.append(chunk)
            yield chunk

        # 流结束后保存完整内容
        full_content = "".join(content_parts)
        if full_content:
            self.context.add_message(Message.assistant(full_content))

    def clear_history(self) -> None:
        """清空对话历史."""
        self.context.clear()
        self.tool_history.clear()

    def get_history(self) -> list[dict[str, Any]]:
        """获取对话历史."""
        return [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in self.context.get_messages()
        ]

    def get_tool_history(self) -> list[dict[str, Any]]:
        """获取工具调用历史."""
        return self.tool_history.copy()


class ChatManager:
    """聊天管理器（支持多会话）."""

    def __init__(self, config: Config | None = None):
        """初始化管理器."""
        self.config = config or Config()
        self.sessions: dict[str, ChatSession] = {}
        self.current_session_id: str | None = None

    def create_session(
        self,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        创建新会话.

        Args:
            session_id: 会话ID（自动生成如果不提供）
            system_prompt: 系统提示词

        Returns:
            会话ID
        """
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())[:8]

        self.sessions[session_id] = ChatSession(
            config=self.config,
            system_prompt=system_prompt,
        )
        self.current_session_id = session_id

        return session_id

    def get_session(self, session_id: str | None = None) -> ChatSession:
        """获取会话."""
        if session_id is None:
            session_id = self.current_session_id

        if session_id is None:
            # 自动创建新会话
            session_id = self.create_session()

        if session_id not in self.sessions:
            raise ValueError(f"会话不存在: {session_id}")

        return self.sessions[session_id]

    def switch_session(self, session_id: str) -> bool:
        """切换当前会话."""
        if session_id in self.sessions:
            self.current_session_id = session_id
            return True
        return False

    def list_sessions(self) -> list[str]:
        """列出所有会话ID."""
        return list(self.sessions.keys())

    def remove_session(self, session_id: str) -> bool:
        """删除会话."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            if self.current_session_id == session_id:
                self.current_session_id = None
            return True
        return False

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        use_tools: bool = True,
    ) -> str:
        """
        发送消息（便捷方法）.

        Args:
            message: 消息内容
            session_id: 会话ID
            use_tools: 是否使用工具

        Returns:
            响应内容
        """
        session = self.get_session(session_id)
        return await session.send_message(message, use_tools=use_tools)
