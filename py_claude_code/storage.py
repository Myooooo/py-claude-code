"""会话持久化存储 - SQLite实现."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict
from contextlib import contextmanager

from .llm import Message


@dataclass
class SessionData:
    """会话数据."""

    session_id: str
    messages: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class SessionStorage:
    """会话存储管理器."""

    def __init__(self, db_path: Optional[str] = None):
        """初始化存储.

        Args:
            db_path: 数据库路径，默认 ~/.py_claude_code/sessions.db
        """
        if db_path is None:
            home = Path.home()
            db_dir = home / ".py_claude_code"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "sessions.db")

        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接上下文."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库表."""
        with self._get_connection() as conn:
            # 会话表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    messages TEXT NOT NULL,
                    tool_history TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)

            # 检查点表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    tool_history TEXT NOT NULL,
                    checkpoint_name TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # 记忆表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

    def save_session(
        self,
        session_id: str,
        messages: list[Message],
        tool_history: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """保存会话.

        Args:
            session_id: 会话ID
            messages: 消息列表
            tool_history: 工具调用历史
            metadata: 元数据
        """
        now = datetime.now().isoformat()

        # 序列化消息
        messages_data = [
            {
                "role": msg.role,
                "content": msg.content,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
                "name": msg.name,
            }
            for msg in messages
        ]

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                (session_id, messages, tool_history, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    json.dumps(messages_data),
                    json.dumps(tool_history),
                    now,
                    now,
                    json.dumps(metadata or {}),
                ),
            )

    def load_session(self, session_id: str) -> Optional[SessionData]:
        """加载会话.

        Args:
            session_id: 会话ID

        Returns:
            会话数据，不存在返回None
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if row is None:
                return None

            return SessionData(
                session_id=row["session_id"],
                messages=json.loads(row["messages"]),
                tool_history=json.loads(row["tool_history"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=json.loads(row["metadata"] or "{}"),
            )

    def delete_session(self, session_id: str) -> bool:
        """删除会话.

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话.

        Returns:
            会话列表
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT session_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()

            return [
                {
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def create_checkpoint(
        self,
        session_id: str,
        messages: list[Message],
        tool_history: list[dict[str, Any]],
        name: Optional[str] = None,
    ) -> int:
        """创建检查点.

        Args:
            session_id: 会话ID
            messages: 消息列表
            tool_history: 工具调用历史
            name: 检查点名称

        Returns:
            检查点ID
        """
        now = datetime.now().isoformat()

        messages_data = [
            {
                "role": msg.role,
                "content": msg.content,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
                "name": msg.name,
            }
            for msg in messages
        ]

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO checkpoints
                (session_id, messages, tool_history, checkpoint_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    json.dumps(messages_data),
                    json.dumps(tool_history),
                    name or f"checkpoint_{now}",
                    now,
                ),
            )
            return cursor.lastrowid

    def get_latest_checkpoint(self, session_id: str) -> Optional[SessionData]:
        """获取最新检查点.

        Args:
            session_id: 会话ID

        Returns:
            检查点数据
        """
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

            if row is None:
                return None

            return SessionData(
                session_id=session_id,
                messages=json.loads(row["messages"]),
                tool_history=json.loads(row["tool_history"]),
                created_at=row["created_at"],
                updated_at=row["created_at"],
                metadata={"checkpoint_id": row["id"], "name": row["checkpoint_name"]},
            )

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        """列出会话的所有检查点.

        Args:
            session_id: 会话ID

        Returns:
            检查点列表
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, checkpoint_name, created_at FROM checkpoints
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ).fetchall()

            return [
                {
                    "id": row["id"],
                    "name": row["checkpoint_name"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def restore_checkpoint(self, checkpoint_id: int) -> Optional[SessionData]:
        """恢复到指定检查点.

        Args:
            checkpoint_id: 检查点ID

        Returns:
            检查点数据
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()

            if row is None:
                return None

            return SessionData(
                session_id=row["session_id"],
                messages=json.loads(row["messages"]),
                tool_history=json.loads(row["tool_history"]),
                created_at=row["created_at"],
                updated_at=row["created_at"],
                metadata={"checkpoint_id": row["id"]},
            )

    def add_memory(
        self,
        session_id: str,
        content: str,
        importance: int = 1,
    ) -> int:
        """添加记忆.

        Args:
            session_id: 会话ID
            content: 记忆内容
            importance: 重要性(1-10)

        Returns:
            记忆ID
        """
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories (session_id, content, importance, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, content, importance, now),
            )
            return cursor.lastrowid

    def get_memories(
        self,
        session_id: str,
        min_importance: int = 1,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """获取记忆.

        Args:
            session_id: 会话ID
            min_importance: 最小重要性
            limit: 数量限制

        Returns:
            记忆列表
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE session_id = ? AND importance >= ?
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (session_id, min_importance, limit),
            ).fetchall()

            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "importance": row["importance"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def clear_old_sessions(self, days: int = 30) -> int:
        """清理旧会话.

        Args:
            days: 保留天数

        Returns:
            删除的会话数
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE updated_at < ?",
                (cutoff,),
            )
            return cursor.rowcount
