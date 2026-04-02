"""记忆管理模块 - 长期记忆存储和召回."""

import json
import sqlite3
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from .storage import SessionStorage


@dataclass
class Memory:
    """记忆条目."""

    id: Optional[int]
    session_id: str
    category: str  # fact, preference, decision, code
    content: str
    importance: int  # 1-10
    source: str  # 来源（user/assistant/tool）
    created_at: str
    last_accessed: str
    access_count: int


class MemoryManager:
    """记忆管理器."""

    def __init__(self, storage: SessionStorage):
        """初始化记忆管理器."""
        self.storage = storage
        self.db_path = storage.db_path
        self._init_memory_table()

    def _init_memory_table(self) -> None:
        """初始化记忆表."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        importance INTEGER DEFAULT 5,
                        source TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        access_count INTEGER DEFAULT 0
                    )
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_session
                    ON memories(session_id)
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_category
                    ON memories(category)
                """)

                conn.commit()
        except Exception as e:
            print(f"初始化记忆表失败: {e}")

    def store_memory(
        self,
        session_id: str,
        content: str,
        category: str = "fact",
        importance: int = 5,
        source: str = "user"
    ) -> bool:
        """存储记忆."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT INTO memories
                    (session_id, category, content, importance, source, created_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (session_id, category, content, importance, source))
                conn.commit()
            return True
        except Exception as e:
            print(f"存储记忆失败: {e}")
            return False

    def extract_and_store(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> list[Memory]:
        """提取并存储记忆."""
        memories = []

        # 提取重要信息
        extracted = self._extract_important_info(role, content)

        for item in extracted:
            if self.store_memory(
                session_id=session_id,
                content=item["content"],
                category=item["category"],
                importance=item["importance"],
                source=role
            ):
                memories.append(Memory(
                    id=None,
                    session_id=session_id,
                    category=item["category"],
                    content=item["content"],
                    importance=item["importance"],
                    source=role,
                    created_at=datetime.now().isoformat(),
                    last_accessed=datetime.now().isoformat(),
                    access_count=0,
                ))

        return memories

    def _extract_important_info(self, role: str, content: str) -> list[dict[str, Any]]:
        """从内容中提取重要信息."""
        results = []

        # 提取文件路径
        file_patterns = [
            r'[\w\-./]+\.py',
            r'[\w\-./]+\.js',
            r'[\w\-./]+\.ts',
            r'[\w\-./]+\.md',
            r'[\w\-./]+\.json',
            r'[\w\-./]+\.yaml',
            r'[\w\-./]+\.yml',
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, content)
            for match in set(matches):
                results.append({
                    "content": f"相关文件: {match}",
                    "category": "code",
                    "importance": 7,
                })

        # 提取配置项
        if "config" in content.lower() or "配置" in content:
            results.append({
                "content": content[:200],
                "category": "preference",
                "importance": 6,
            })

        # 提取决策点
        if any(word in content.lower() for word in ["decision", "决定", "选择", "使用"]):
            if len(content) < 500:
                results.append({
                    "content": content,
                    "category": "decision",
                    "importance": 8,
                })

        # 限制数量
        return results[:5]

    def get_relevant_memories(
        self,
        session_id: str,
        query: str,
        limit: int = 5
    ) -> list[Memory]:
        """获取相关记忆."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                # 简单关键词匹配
                keywords = [w for w in query.lower().split() if len(w) > 2]

                if not keywords:
                    # 获取最近的高重要性记忆
                    cursor = conn.execute("""
                        SELECT * FROM memories
                        WHERE session_id = ?
                        ORDER BY importance DESC, last_accessed DESC
                        LIMIT ?
                    """, (session_id, limit))
                else:
                    # 基于关键词匹配
                    conditions = " OR ".join(["content LIKE ?"] * len(keywords))
                    params = [session_id] + [f"%{k}%" for k in keywords] + [limit]

                    cursor = conn.execute(f"""
                        SELECT * FROM memories
                        WHERE session_id = ? AND ({conditions})
                        ORDER BY importance DESC, last_accessed DESC
                        LIMIT ?
                    """, params)

                memories = []
                for row in cursor.fetchall():
                    memories.append(Memory(
                        id=row["id"],
                        session_id=row["session_id"],
                        category=row["category"],
                        content=row["content"],
                        importance=row["importance"],
                        source=row["source"],
                        created_at=row["created_at"],
                        last_accessed=row["last_accessed"],
                        access_count=row["access_count"],
                    ))

                # 更新访问统计
                for mem in memories:
                    if mem.id:
                        conn.execute("""
                            UPDATE memories
                            SET access_count = access_count + 1,
                                last_accessed = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (mem.id,))

                conn.commit()
                return memories

        except Exception as e:
            print(f"获取记忆失败: {e}")
            return []

    def format_memories_for_prompt(self, memories: list[Memory]) -> str:
        """格式化记忆为提示词."""
        if not memories:
            return ""

        lines = ["[相关记忆]"]
        for mem in memories[:3]:  # 最多3条
            lines.append(f"- {mem.content}")

        return "\n".join(lines)

    def get_session_memories(
        self,
        session_id: str,
        category: Optional[str] = None
    ) -> list[Memory]:
        """获取会话的所有记忆."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                if category:
                    cursor = conn.execute(
                        """SELECT * FROM memories
                           WHERE session_id = ? AND category = ?
                           ORDER BY importance DESC, created_at DESC""",
                        (session_id, category)
                    )
                else:
                    cursor = conn.execute(
                        """SELECT * FROM memories
                           WHERE session_id = ?
                           ORDER BY importance DESC, created_at DESC""",
                        (session_id,)
                    )

                return [
                    Memory(
                        id=row["id"],
                        session_id=row["session_id"],
                        category=row["category"],
                        content=row["content"],
                        importance=row["importance"],
                        source=row["source"],
                        created_at=row["created_at"],
                        last_accessed=row["last_accessed"],
                        access_count=row["access_count"],
                    )
                    for row in cursor.fetchall()
                ]

        except Exception as e:
            print(f"获取会话记忆失败: {e}")
            return []

    def delete_memory(self, memory_id: int) -> bool:
        """删除记忆."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "DELETE FROM memories WHERE id = ?",
                    (memory_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"删除记忆失败: {e}")
            return False

    def cleanup_old_memories(self, days: int = 30) -> int:
        """清理旧记忆."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "DELETE FROM memories WHERE last_accessed < ?",
                    (cutoff.isoformat(),)
                )
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"清理旧记忆失败: {e}")
            return 0

    def get_memory_stats(self, session_id: Optional[str] = None) -> dict[str, Any]:
        """获取记忆统计."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                if session_id:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as count FROM memories WHERE session_id = ?",
                        (session_id,)
                    )
                    total = cursor.fetchone()["count"]

                    cursor = conn.execute(
                        """SELECT category, COUNT(*) as count
                           FROM memories WHERE session_id = ?
                           GROUP BY category""",
                        (session_id,)
                    )
                    by_category = {row["category"]: row["count"] for row in cursor.fetchall()}
                else:
                    cursor = conn.execute("SELECT COUNT(*) as count FROM memories")
                    total = cursor.fetchone()["count"]

                    cursor = conn.execute(
                        """SELECT category, COUNT(*) as count
                           FROM memories GROUP BY category"""
                    )
                    by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

                return {
                    "total_memories": total,
                    "by_category": by_category,
                }
        except Exception as e:
            print(f"获取记忆统计失败: {e}")
            return {"total_memories": 0, "by_category": {}}
