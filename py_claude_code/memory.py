"""长期记忆系统."""

import re
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .storage import SessionStorage


@dataclass
class Memory:
    """记忆条目."""

    content: str
    importance: int = 1
    category: str = "general"
    timestamp: str = ""


class MemoryExtractor:
    """记忆提取器 - 从对话中提取重要信息."""

    # 需要记忆的实体类型
    ENTITY_PATTERNS = {
        "file": r"([\w\-/.]+\.(py|js|ts|json|md|txt|yaml|yml))",
        "url": r"(https?://[^\s]+)",
        "email": r"([\w.-]+@[\w.-]+\.[a-zA-Z]{2,})",
        "command": r"(pip install|npm install|git clone|docker run)\s+([\w\-/.:@]+)",
    }

    # 重要关键词
    IMPORTANT_KEYWORDS = [
        "重要",
        "关键",
        "记住",
        "保存",
        "必须",
        "不要忘",
        "note",
        "important",
        "remember",
        "key",
    ]

    def __init__(self):
        """初始化提取器."""
        self.compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.ENTITY_PATTERNS.items()
        }

    def extract_from_message(
        self,
        role: str,
        content: str,
    ) -> list[Memory]:
        """从消息中提取记忆.

        Args:
            role: 消息角色
            content: 消息内容

        Returns:
            提取的记忆列表
        """
        memories = []

        if not content:
            return memories

        # 提取实体
        for entity_type, pattern in self.compiled_patterns.items():
            matches = pattern.findall(content)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match[0] else match[1]

                entity_memory = Memory(
                    content=f"[实体] {entity_type}: {match}",
                    importance=3,
                    category="entity",
                    timestamp=datetime.now().isoformat(),
                )
                memories.append(entity_memory)

        # 检测重要语句
        for keyword in self.IMPORTANT_KEYWORDS:
            if keyword.lower() in content.lower():
                # 提取包含关键词的句子
                sentences = content.split("。")
                for sentence in sentences:
                    if keyword.lower() in sentence.lower():
                        important_memory = Memory(
                            content=f"[重要] {sentence.strip()}",
                            importance=5,
                            category="important",
                            timestamp=datetime.now().isoformat(),
                        )
                        memories.append(important_memory)
                        break

        # 提取决策信息（助手回复中的结论）
        if role == "assistant":
            decision_patterns = [
                r"结论[是:：]\s*([^。]+)",
                r"应该[是:：]\s*([^。]+)",
                r"建议[是:：]\s*([^。]+)",
                r"需要[是:：]\s*([^。]+)",
            ]
            for pattern in decision_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    decision_memory = Memory(
                        content=f"[决策] {match.strip()}",
                        importance=4,
                        category="decision",
                        timestamp=datetime.now().isoformat(),
                    )
                    memories.append(decision_memory)

        return memories

    def extract_from_tool_result(
        self,
        tool_name: str,
        result: Any,
    ) -> list[Memory]:
        """从工具结果中提取记忆.

        Args:
            tool_name: 工具名称
            result: 工具结果

        Returns:
            提取的记忆列表
        """
        memories = []

        # 提取文件操作
        if tool_name in ["file_write", "file_edit"]:
            if hasattr(result, "data") and result.data:
                file_path = result.data.get("file_path", "")
                if file_path:
                    memories.append(
                        Memory(
                            content=f"[文件操作] 修改了文件: {file_path}",
                            importance=4,
                            category="file_operation",
                            timestamp=datetime.now().isoformat(),
                        )
                    )

        # 提取命令执行
        elif tool_name == "bash":
            if hasattr(result, "data") and result.data:
                command = result.data.get("command", "")
                if command:
                    memories.append(
                        Memory(
                            content=f"[命令执行] 执行了: {command}",
                            importance=3,
                            category="command",
                            timestamp=datetime.now().isoformat(),
                        )
                    )

        return memories


class MemoryManager:
    """记忆管理器."""

    def __init__(self, storage: Optional[SessionStorage] = None):
        """初始化记忆管理器.

        Args:
            storage: 存储实例
        """
        self.storage = storage or SessionStorage()
        self.extractor = MemoryExtractor()

    def add_memory(
        self,
        session_id: str,
        content: str,
        importance: int = 1,
    ) -> int:
        """手动添加记忆.

        Args:
            session_id: 会话ID
            content: 记忆内容
            importance: 重要性

        Returns:
            记忆ID
        """
        return self.storage.add_memory(session_id, content, importance)

    def extract_and_store(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> list[int]:
        """提取并存储记忆.

        Args:
            session_id: 会话ID
            role: 消息角色
            content: 消息内容

        Returns:
            记忆ID列表
        """
        memories = self.extractor.extract_from_message(role, content)
        memory_ids = []

        for memory in memories:
            memory_id = self.storage.add_memory(
                session_id,
                memory.content,
                memory.importance,
            )
            memory_ids.append(memory_id)

        return memory_ids

    def get_relevant_memories(
        self,
        session_id: str,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """获取相关记忆.

        Args:
            session_id: 会话ID
            query: 查询内容（可选）
            limit: 数量限制

        Returns:
            记忆列表
        """
        # 获取高重要性记忆
        memories = self.storage.get_memories(
            session_id,
            min_importance=3,
            limit=limit,
        )

        # 如果有查询，进行简单匹配
        if query and memories:
            query_keywords = set(query.lower().split())
            scored_memories = []

            for memory in memories:
                content = memory.get("content", "").lower()
                score = sum(1 for kw in query_keywords if kw in content)
                scored_memories.append((score, memory))

            # 按相关性排序
            scored_memories.sort(key=lambda x: x[0], reverse=True)
            memories = [m for _, m in scored_memories]

        return memories

    def format_memories_for_prompt(
        self,
        memories: list[dict[str, Any]],
    ) -> str:
        """将记忆格式化为提示词.

        Args:
            memories: 记忆列表

        Returns:
            格式化字符串
        """
        if not memories:
            return ""

        lines = ["\n[相关背景信息]"]

        for i, memory in enumerate(memories, 1):
            content = memory.get("content", "")
            category = memory.get("importance", 1)
            lines.append(f"{i}. {content}")

        lines.append("[/相关背景信息]\n")

        return "\n".join(lines)

    def clear_session_memories(self, session_id: str) -> None:
        """清空会话记忆.

        Args:
            session_id: 会话ID
        """
        # 这里需要添加storage的方法
        # 暂时不实现
        pass
