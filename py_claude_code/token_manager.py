"""Token管理模块 - 基于tiktoken的上下文管理."""

import json
from dataclasses import dataclass
from typing import Any

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from .llm import Message


@dataclass
class TokenMetrics:
    """Token使用统计."""

    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    max_tokens: int
    usage_percentage: float


class TokenManager:
    """Token管理器 - 管理上下文和工具结果摘要."""

    # 摘要阈值
    SUMMARIZE_THRESHOLD = 1000  # 超过此token数需要摘要
    SUMMARIZE_HEAD_KEEP = 200   # 摘要保留开头字符数
    SUMMARIZE_TAIL_KEEP = 200   # 摘要保留结尾字符数

    def __init__(self, model: str = "gpt-4", max_tokens: int = 100000):
        """初始化Token管理器."""
        self.model = model
        self.max_tokens = max_tokens
        self._encoding = None
        self._init_encoder()

    def _init_encoder(self) -> None:
        """初始化tiktoken编码器."""
        if not TIKTOKEN_AVAILABLE:
            return

        try:
            if "gpt-4" in self.model or "gpt-3.5" in self.model:
                self._encoding = tiktoken.get_encoding("cl100k_base")
            else:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            try:
                self._encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self._encoding = None

    def count_tokens(self, text: str) -> int:
        """计算文本的token数."""
        if not self._encoding:
            return len(text) // 4

        try:
            return len(self._encoding.encode(text))
        except Exception:
            return len(text) // 4

    def count_message_tokens(self, message: Message) -> int:
        """计算单条消息的token数."""
        overhead = 4
        content = message.content or ""
        token_count = self.count_tokens(content) + overhead

        if message.tool_calls:
            for tc in message.tool_calls:
                token_count += self.count_tokens(json.dumps(tc))
            token_count += 4

        if message.tool_call_id:
            token_count += self.count_tokens(message.tool_call_id)

        if message.name:
            token_count += self.count_tokens(message.name)

        return token_count

    def count_messages_tokens(self, messages: list[Message]) -> int:
        """计算消息列表的总token数."""
        return sum(self.count_message_tokens(msg) for msg in messages)

    def get_metrics(self, messages: list[Message]) -> TokenMetrics:
        """获取Token使用统计."""
        total = self.count_messages_tokens(messages)
        prompt_tokens = sum(
            self.count_message_tokens(msg)
            for msg in messages
            if msg.role in ("system", "user", "tool")
        )
        completion_tokens = total - prompt_tokens

        return TokenMetrics(
            total_tokens=total,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            max_tokens=self.max_tokens,
            usage_percentage=(total / self.max_tokens * 100) if self.max_tokens > 0 else 0,
        )

    def compress_context(self, messages: list[Message], preserve_recent: int = 6) -> list[Message]:
        """压缩上下文以符合token限制."""
        if not messages:
            return []

        system_msgs = [m for m in messages if m.role == "system"]
        other_msgs = [m for m in messages if m.role != "system"]

        if len(other_msgs) <= preserve_recent:
            return messages

        recent_msgs = other_msgs[-preserve_recent:]
        old_msgs = other_msgs[:-preserve_recent]

        if old_msgs:
            summary = self._create_summary(old_msgs)
            summary_msg = Message.assistant(f"[历史对话摘要] {summary}")
            return system_msgs + [summary_msg] + recent_msgs

        return system_msgs + recent_msgs

    def _create_summary(self, messages: list[Message]) -> str:
        """创建消息摘要."""
        parts = []
        for msg in messages:
            if msg.role == "user":
                content = (msg.content or "")[:100]
                parts.append(f"用户: {content}...")
            elif msg.role == "assistant" and not msg.tool_calls:
                content = (msg.content or "")[:100]
                parts.append(f"助手: {content}...")

        return " | ".join(parts[:3])

    def summarize_tool_result(self, content: str, max_tokens: int = 500) -> str:
        """摘要工具结果（如果过长）."""
        token_count = self.count_tokens(content)

        if token_count <= self.SUMMARIZE_THRESHOLD:
            return content

        head_chars = self.SUMMARIZE_HEAD_KEEP
        tail_chars = self.SUMMARIZE_TAIL_KEEP

        head = content[:head_chars]
        tail = content[-tail_chars:] if len(content) > tail_chars else ""

        omitted_tokens = token_count - self.count_tokens(head) - self.count_tokens(tail)

        if tail:
            return f"{head}\n\n... [省略 {omitted_tokens} tokens] ...\n\n{tail}"
        else:
            return f"{head}\n\n... [省略 {omitted_tokens} tokens] ..."

    def should_compress(self, messages: list[Message]) -> bool:
        """检查是否需要压缩上下文."""
        return self.count_messages_tokens(messages) > self.max_tokens * 0.9

    def get_compression_suggestion(self, messages: list[Message]) -> dict[str, Any]:
        """获取压缩建议."""
        metrics = self.get_metrics(messages)

        return {
            "should_compress": self.should_compress(messages),
            "current_usage": f"{metrics.usage_percentage:.1f}%",
            "total_tokens": metrics.total_tokens,
            "max_tokens": self.max_tokens,
            "message_count": len(messages),
            "suggestion": (
                "建议压缩上下文" if self.should_compress(messages)
                else "上下文大小正常"
            ),
        }
