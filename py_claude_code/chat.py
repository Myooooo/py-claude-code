"""对话管理模块 - 集成Token管理、持久化和记忆系统."""

import json
import uuid
from typing import Any, AsyncIterator, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .config import Config
from .llm import Message, OpenAIClient, LLMResponse
from .tools.base import ToolResult
from .token_manager import TokenManager, TokenMetrics
from .storage import SessionStorage, SessionData
from .memory import MemoryManager
from .cost_tracker import CostTracker, CostSummary, get_cost_tracker


@dataclass
class ConversationContext:
    """对话上下文 - 支持Token管理和智能压缩."""

    messages: list[Message] = field(default_factory=list)
    max_messages: int = 50
    max_tokens: int = 100000
    preserve_recent: int = 6

    def __post_init__(self):
        """初始化Token管理器."""
        self.token_manager: Optional[TokenManager] = None

    def set_token_manager(self, token_manager: TokenManager) -> None:
        """设置Token管理器."""
        self.token_manager = token_manager

    def add_message(self, message: Message) -> None:
        """添加消息，自动管理上下文长度."""
        self.messages.append(message)

        # 使用Token管理进行智能压缩
        if self.token_manager:
            current_tokens = self.token_manager.count_messages_tokens(self.messages)
            if current_tokens > self.max_tokens:
                self.messages = self.token_manager.compress_context(
                    self.messages,
                    preserve_recent=self.preserve_recent,
                )
        else:
            # 回退到消息数限制
            if len(self.messages) > self.max_messages:
                system_msgs = [m for m in self.messages if m.role == "system"]
                other_msgs = [m for m in self.messages if m.role != "system"]
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
        self.messages = [m for m in self.messages if m.role != "system"]
        self.messages.insert(0, Message.system(content))

    def get_token_metrics(self) -> Optional[TokenMetrics]:
        """获取Token使用统计."""
        if self.token_manager:
            return self.token_manager.get_metrics(self.messages)
        return None


class Checkpoint:
    """对话检查点."""

    def __init__(
        self,
        name: str,
        messages: list[Message],
        tool_history: list[dict[str, Any]],
    ):
        """初始化检查点."""
        self.name = name
        self.messages = messages.copy()
        self.tool_history = tool_history.copy()
        self.created_at = datetime.now().isoformat()


class ChatSession:
    """聊天会话 - 集成持久化和记忆."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        config: Optional[Config] = None,
        system_prompt: Optional[str] = None,
        storage: Optional[SessionStorage] = None,
        enable_cost_tracking: bool = True,
    ):
        """初始化会话."""
        self.session_id = session_id or self._generate_session_id()
        self.config = config or Config()
        self.enable_cost_tracking = enable_cost_tracking
        self.client = OpenAIClient(
            self.config,
            session_id=self.session_id,
            enable_cost_tracking=enable_cost_tracking,
        )

        # 初始化Token管理器
        self.token_manager = TokenManager(
            model=self.config.model,
            max_tokens=self.config.max_context_tokens,
        )

        # 初始化上下文
        self.context = ConversationContext(
            max_messages=self.config.max_context_messages,
            max_tokens=self.config.max_context_tokens,
        )
        self.context.set_token_manager(self.token_manager)

        # 设置系统提示词
        if system_prompt:
            self.context.set_system_message(system_prompt)
        else:
            self.context.set_system_message(self.config.system_prompt)

        # 工具历史
        self.tool_history: list[dict[str, Any]] = []
        self.full_tool_results: dict[str, str] = {}  # 存储完整工具结果

        # 持久化存储
        self.storage = storage

        # 成本追踪
        self.cost_tracker: Optional[CostTracker] = None
        if self.enable_cost_tracking:
            self.cost_tracker = get_cost_tracker()

        # 记忆管理
        self.memory_manager: Optional[MemoryManager] = None
        if self.storage:
            self.memory_manager = MemoryManager(self.storage)

        # 检查点
        self.checkpoints: list[Checkpoint] = []
        self.current_checkpoint_index: int = -1

        # 自动保存计数
        self.message_count_since_save: int = 0
        self.auto_save_interval: int = 5

    def _generate_session_id(self) -> str:
        """生成会话ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    async def send_message(
        self,
        content: str,
        use_tools: bool = True,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """发送消息."""
        # 召回相关记忆
        if self.memory_manager:
            memories = self.memory_manager.get_relevant_memories(
                self.session_id,
                query=content,
                limit=3,
            )
            if memories:
                memory_prompt = self.memory_manager.format_memories_for_prompt(memories)
                content = f"{memory_prompt}\n\n当前问题: {content}"

        # 添加用户消息
        self.context.add_message(Message.user(content))

        # 提取并存储记忆
        if self.memory_manager:
            await self._extract_memory("user", content)

        if use_tools:
            result = await self._chat_with_tools(stream)
        else:
            result = await self._simple_chat(stream)

        # 自动保存
        self.message_count_since_save += 1
        if self.message_count_since_save >= self.auto_save_interval:
            self._auto_save()
            self.message_count_since_save = 0

        return result

    async def _extract_memory(self, role: str, content: str) -> None:
        """提取并存储记忆."""
        if not self.memory_manager:
            return

        try:
            self.memory_manager.extract_and_store(
                self.session_id,
                role,
                content,
            )
        except Exception:
            pass  # 记忆提取失败不影响主流程

    async def _simple_chat(self, stream: bool) -> str | AsyncIterator[str]:
        """简单对话."""
        messages = self.context.get_messages()
        response = await self.client.chat(messages, stream=stream)

        if stream:
            return self._handle_stream(response)
        else:
            if isinstance(response, LLMResponse):
                if response.content:
                    self.context.add_message(Message.assistant(response.content))
                    if self.memory_manager:
                        await self._extract_memory("assistant", response.content)
                return response.content or ""
            return ""

    async def _chat_with_tools(
        self,
        stream: bool
    ) -> str | AsyncIterator[str]:
        """支持工具调用的对话."""
        messages = self.context.get_messages()

        tool_results: list[tuple[str, ToolResult]] = []

        def on_tool_call(name: str, result: ToolResult) -> None:
            """工具调用回调 - 支持结果摘要."""
            tool_results.append((name, result))

            # 存储完整结果
            result_id = f"{name}_{len(self.tool_history)}"
            self.full_tool_results[result_id] = result.content

            # 摘要显示
            display_content = result.content
            if self.token_manager:
                display_content = self.token_manager.summarize_tool_result(
                    result.content,
                    max_tokens=500,
                )

            self.tool_history.append({
                "tool": name,
                "success": result.success,
                "content": display_content[:200] if len(display_content) > 200 else display_content,
                "full_result_id": result_id,
            })

        response = await self.client.chat_with_tools(
            messages,
            max_iterations=self.config.max_tool_iterations,
            tool_callback=on_tool_call,
        )

        assistant_content = response.content or ""
        self.context.add_message(Message.assistant(assistant_content))

        if self.memory_manager:
            await self._extract_memory("assistant", assistant_content)

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

        full_content = "".join(content_parts)
        if full_content:
            self.context.add_message(Message.assistant(full_content))
            if self.memory_manager:
                await self._extract_memory("assistant", full_content)

    def create_checkpoint(self, name: Optional[str] = None) -> str:
        """创建检查点."""
        if name is None:
            name = f"checkpoint_{len(self.checkpoints) + 1}"

        checkpoint = Checkpoint(
            name=name,
            messages=self.context.get_messages(),
            tool_history=self.tool_history.copy(),
        )

        self.checkpoints.append(checkpoint)
        self.current_checkpoint_index = len(self.checkpoints) - 1

        # 保存到数据库
        if self.storage:
            try:
                self.storage.create_checkpoint(
                    self.session_id,
                    self.context.get_messages(),
                    self.tool_history,
                    name,
                )
            except Exception:
                pass

        return name

    def undo(self) -> bool:
        """回滚到上一检查点."""
        if self.current_checkpoint_index > 0:
            self.current_checkpoint_index -= 1
            self._restore_checkpoint(self.checkpoints[self.current_checkpoint_index])
            return True
        return False

    def redo(self) -> bool:
        """恢复检查点."""
        if self.current_checkpoint_index < len(self.checkpoints) - 1:
            self.current_checkpoint_index += 1
            self._restore_checkpoint(self.checkpoints[self.current_checkpoint_index])
            return True
        return False

    def _restore_checkpoint(self, checkpoint: Checkpoint) -> None:
        """恢复检查点状态."""
        self.context.messages = checkpoint.messages.copy()
        self.tool_history = checkpoint.tool_history.copy()

    def _auto_save(self) -> None:
        """自动保存会话."""
        if not self.storage:
            return

        try:
            cost_summary = self.get_cost_summary()
            self.storage.save_session(
                self.session_id,
                self.context.get_messages(),
                self.tool_history,
                metadata={
                    "token_metrics": self.context.get_token_metrics().__dict__ if self.context.get_token_metrics() else {},
                    "checkpoint_count": len(self.checkpoints),
                    "cost_summary": cost_summary.to_dict(),
                },
            )
        except Exception:
            pass

    def save(self) -> None:
        """手动保存会话."""
        self._auto_save()

    def load(self) -> bool:
        """加载会话."""
        if not self.storage:
            return False

        try:
            data = self.storage.load_session(self.session_id)
            if data:
                # 恢复消息
                self.context.messages = [
                    Message(
                        role=msg["role"],
                        content=msg.get("content"),
                        tool_calls=msg.get("tool_calls"),
                        tool_call_id=msg.get("tool_call_id"),
                        name=msg.get("name"),
                    )
                    for msg in data.messages
                ]
                # 恢复工具历史
                self.tool_history = data.tool_history
                return True
        except Exception:
            pass

        return False

    def clear_history(self) -> None:
        """清空对话历史."""
        self.context.clear()
        self.tool_history.clear()
        self.full_tool_results.clear()

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

    def get_full_tool_result(self, result_id: str) -> Optional[str]:
        """获取完整工具结果."""
        return self.full_tool_results.get(result_id)

    def get_token_metrics(self) -> Optional[TokenMetrics]:
        """获取Token使用统计."""
        return self.context.get_token_metrics()

    def get_cost_summary(self) -> CostSummary:
        """获取会话成本汇总."""
        if self.cost_tracker:
            return self.cost_tracker.get_session_costs(self.session_id)
        return CostSummary(period=f"session:{self.session_id}")

    def get_last_request_cost(self) -> float:
        """获取最后一次请求的成本."""
        return self.client.last_cost

    def get_session_cost(self) -> float:
        """获取会话总成本."""
        return self.client.session_cost

    def check_budget_warnings(self) -> list[dict[str, Any]]:
        """检查预算警告."""
        if self.cost_tracker:
            return self.cost_tracker.check_budget_warnings()
        return []


class ChatManager:
    """聊天管理器 - 支持持久化存储."""

    def __init__(
        self,
        config: Optional[Config] = None,
        enable_cost_tracking: bool = True,
    ):
        """初始化管理器."""
        self.config = config or Config()
        self.enable_cost_tracking = enable_cost_tracking
        self.sessions: dict[str, ChatSession] = {}
        self.current_session_id: Optional[str] = None
        self.storage = SessionStorage()
        self.cost_tracker: Optional[CostTracker] = None
        if enable_cost_tracking:
            self.cost_tracker = get_cost_tracker()

    def create_session(
        self,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """创建新会话."""
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())[:8]

        session = ChatSession(
            session_id=session_id,
            config=self.config,
            system_prompt=system_prompt,
            storage=self.storage,
            enable_cost_tracking=self.enable_cost_tracking,
        )

        # 尝试加载已有会话
        session.load()

        self.sessions[session_id] = session
        self.current_session_id = session_id

        return session_id

    def get_session(self, session_id: Optional[str] = None) -> ChatSession:
        """获取会话."""
        if session_id is None:
            session_id = self.current_session_id

        if session_id is None:
            session_id = self.create_session()

        if session_id not in self.sessions:
            # 尝试从存储加载
            self.create_session(session_id)

        return self.sessions[session_id]

    def switch_session(self, session_id: str) -> bool:
        """切换当前会话."""
        if session_id in self.sessions:
            self.current_session_id = session_id
            return True

        # 尝试加载
        try:
            self.create_session(session_id)
            return True
        except Exception:
            return False

    def list_sessions(self) -> list[str]:
        """列出所有会话ID."""
        # 包括存储中的会话
        stored_sessions = self.storage.list_sessions()
        stored_ids = [s["session_id"] for s in stored_sessions]

        # 合并内存和存储的会话
        all_ids = set(self.sessions.keys()) | set(stored_ids)
        return list(all_ids)

    def remove_session(self, session_id: str) -> bool:
        """删除会话."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            if self.current_session_id == session_id:
                self.current_session_id = None

        # 从存储删除
        try:
            self.storage.delete_session(session_id)
            return True
        except Exception:
            return False

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        use_tools: bool = True,
    ) -> str:
        """发送消息（便捷方法）."""
        session = self.get_session(session_id)
        return await session.send_message(message, use_tools=use_tools)

    def get_cost_summary(self, period: str = "all_time") -> dict[str, Any]:
        """获取成本汇总.

        Args:
            period: 周期 (daily, weekly, monthly, all_time)
        """
        if not self.cost_tracker:
            return {}

        if period == "daily":
            summary = self.cost_tracker.get_daily_summary()
        elif period == "weekly":
            summary = self.cost_tracker.get_weekly_summary()
        elif period == "monthly":
            summary = self.cost_tracker.get_monthly_summary()
        else:
            summary = self.cost_tracker.get_all_time_summary()

        return summary.to_dict()

    def check_budget_warnings(self) -> list[dict[str, Any]]:
        """检查预算警告."""
        if self.cost_tracker:
            return self.cost_tracker.check_budget_warnings()
        return []

    def export_cost_report(self, format: str = "markdown", period: str = "monthly") -> str:
        """导出成本报告."""
        if self.cost_tracker:
            return self.cost_tracker.export_report(format=format, period=period)
        return ""
