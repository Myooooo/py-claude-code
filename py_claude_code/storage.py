"""持久化存储模块 - SQLite实现."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .llm import Message


@dataclass
class SessionData:
    """会话数据."""

    session_id: str
    messages: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class SessionStorage:
    """会话存储 - SQLite实现."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str = ".claude_sessions.db"):
        """初始化存储."""
        self.db_path = Path(db_path)
        self._ensure_db_dir()
        self._init_tables()

    def _ensure_db_dir(self) -> None:
        """确保数据库目录存在."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """初始化数据库表."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                INSERT OR REPLACE INTO metadata (key, value, updated_at)
                VALUES ('schema_version', ?, CURRENT_TIMESTAMP)
            """, (str(self.SCHEMA_VERSION),))

            conn.commit()

    def save_session(
        self,
        session_id: str,
        messages: list[Message],
        tool_history: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """保存会话."""
        try:
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

            data = {
                "session_id": session_id,
                "messages": messages_data,
                "tool_history": tool_history,
                "metadata": metadata or {},
                "updated_at": datetime.now().isoformat(),
            }

            json_data = json.dumps(data, ensure_ascii=False)

            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO sessions (session_id, data, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET
                        data = excluded.data,
                        updated_at = CURRENT_TIMESTAMP
                """, (session_id, json_data))
                conn.commit()
            return True
        except Exception as e:
            print(f"保存会话失败: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[SessionData]:
        """加载会话."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT data FROM sessions WHERE session_id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()

                if row:
                    data = json.loads(row["data"])
                    return SessionData(
                        session_id=session_id,
                        messages=data.get("messages", []),
                        tool_history=data.get("tool_history", []),
                        metadata=data.get("metadata", {}),
                        created_at=data.get("created_at", ""),
                        updated_at=data.get("updated_at", ""),
                    )
                return None
        except Exception as e:
            print(f"加载会话失败: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """删除会话."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (session_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"删除会话失败: {e}")
            return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """SELECT session_id, created_at, updated_at
                       FROM sessions ORDER BY updated_at DESC"""
                )
                return [
                    {
                        "session_id": row["session_id"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            print(f"列出会话失败: {e}")
            return []

    def create_checkpoint(
        self,
        session_id: str,
        messages: list[Message],
        tool_history: list[dict[str, Any]],
        name: str
    ) -> bool:
        """创建检查点."""
        try:
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

            data = {
                "messages": messages_data,
                "tool_history": tool_history,
            }

            json_data = json.dumps(data, ensure_ascii=False)

            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO checkpoints (session_id, name, data)
                    VALUES (?, ?, ?)
                """, (session_id, name, json_data))
                conn.commit()
            return True
        except Exception as e:
            print(f"创建检查点失败: {e}")
            return False

    def load_checkpoint(self, session_id: str, name: str) -> Optional[SessionData]:
        """加载检查点."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """SELECT data FROM checkpoints
                       WHERE session_id = ? AND name = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (session_id, name)
                )
                row = cursor.fetchone()

                if row:
                    data = json.loads(row["data"])
                    return SessionData(
                        session_id=session_id,
                        messages=data.get("messages", []),
                        tool_history=data.get("tool_history", []),
                        metadata={},
                        created_at="",
                        updated_at="",
                    )
                return None
        except Exception as e:
            print(f"加载检查点失败: {e}")
            return None

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """清理旧会话."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE updated_at < ?",
                    (cutoff.isoformat(),)
                )
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"清理旧会话失败: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """获取存储统计."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM sessions")
                total = cursor.fetchone()["count"]

                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

                return {
                    "total_sessions": total,
                    "db_path": str(self.db_path),
                    "db_size_bytes": db_size,
                    "db_size_mb": round(db_size / (1024 * 1024), 2),
                }
        except Exception as e:
            print(f"获取统计失败: {e}")
            return {"total_sessions": 0, "db_path": str(self.db_path), "db_size_bytes": 0, "db_size_mb": 0}
