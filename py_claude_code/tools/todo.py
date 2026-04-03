"""待办事项管理工具.

适用于国企内网/信创环境：纯本地存储，无网络依赖.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry


class TodoItem(BaseTool):
    """待办事项数据模型."""

    id: str = Field(..., description="待办事项ID")
    content: str = Field(..., description="待办内容")
    status: Literal["todo", "in_progress", "done"] = Field(default="todo")
    priority: Literal["low", "medium", "high"] = Field(default="medium")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = Field(default_factory=list)
    file_path: str | None = Field(default=None, description="关联文件路径")


class TodoWriteParams(ToolParameters):
    """待办事项操作参数."""

    operation: Literal["create", "update", "delete", "list", "clear"] = Field(
        default="create",
        description="操作类型: create(创建), update(更新), delete(删除), list(列表), clear(清空)"
    )
    todo_id: str | None = Field(
        default=None,
        description="待办事项ID (update/delete时使用)"
    )
    content: str | None = Field(
        default=None,
        description="待办内容 (create/update时使用)"
    )
    status: Literal["todo", "in_progress", "done"] | None = Field(
        default=None,
        description="状态 (update时使用)"
    )
    priority: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="优先级 (create/update时使用)"
    )
    tags: list[str] | None = Field(
        default=None,
        description="标签列表 (create/update时使用)"
    )
    file_path: str | None = Field(
        default=None,
        description="关联文件路径，用于按文件管理待办"
    )
    filter_status: Literal["todo", "in_progress", "done", "all"] | None = Field(
        default=None,
        description="过滤状态 (list时使用)"
    )
    filter_priority: Literal["low", "medium", "high", "all"] | None = Field(
        default=None,
        description="过滤优先级 (list时使用)"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None, info) -> str | None:
        """验证内容不为空（创建时）."""
        if info.data.get("operation") == "create" and (not v or not v.strip()):
            raise ValueError("创建待办时内容不能为空")
        return v.strip() if v else v


class TodoManager:
    """待办事项管理器."""

    def __init__(self) -> None:
        """初始化待办管理器."""
        # 存储路径: ~/.claude/todos.json
        self.storage_path = Path.home() / ".claude" / "todos.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._todos: list[dict] = []
        self._load()

    def _load(self) -> None:
        """从文件加载待办事项."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._todos = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._todos = []
        else:
            self._todos = []

    def _save(self) -> None:
        """保存待办事项到文件."""
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._todos, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> str:
        """生成唯一ID."""
        import uuid
        return f"todo_{uuid.uuid4().hex[:8]}"

    def create(
        self,
        content: str,
        priority: str = "medium",
        status: str = "todo",
        tags: list[str] | None = None,
        file_path: str | None = None
    ) -> dict:
        """创建待办事项."""
        todo = {
            "id": self._generate_id(),
            "content": content,
            "status": status,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "tags": tags or [],
            "file_path": file_path,
        }
        self._todos.append(todo)
        self._save()
        return todo

    def update(
        self,
        todo_id: str,
        content: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None
    ) -> dict | None:
        """更新待办事项."""
        for todo in self._todos:
            if todo["id"] == todo_id:
                if content is not None:
                    todo["content"] = content
                if status is not None:
                    todo["status"] = status
                if priority is not None:
                    todo["priority"] = priority
                if tags is not None:
                    todo["tags"] = tags
                todo["updated_at"] = datetime.now().isoformat()
                self._save()
                return todo
        return None

    def delete(self, todo_id: str) -> bool:
        """删除待办事项."""
        for i, todo in enumerate(self._todos):
            if todo["id"] == todo_id:
                del self._todos[i]
                self._save()
                return True
        return False

    def list(
        self,
        file_path: str | None = None,
        status: str | None = None,
        priority: str | None = None
    ) -> list[dict]:
        """列出待办事项."""
        result = self._todos

        if file_path:
            result = [t for t in result if t.get("file_path") == file_path]

        if status and status != "all":
            result = [t for t in result if t["status"] == status]

        if priority and priority != "all":
            result = [t for t in result if t["priority"] == priority]

        # 按优先级和创建时间排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        result.sort(key=lambda t: (priority_order.get(t["priority"], 1), t["created_at"]))

        return result

    def clear(self, file_path: str | None = None) -> int:
        """清空待办事项."""
        if file_path:
            count = len([t for t in self._todos if t.get("file_path") == file_path])
            self._todos = [t for t in self._todos if t.get("file_path") != file_path]
        else:
            count = len(self._todos)
            self._todos = []

        self._save()
        return count


# 模块级单例管理器
_todo_manager: TodoManager | None = None


def _get_todo_manager() -> TodoManager:
    """获取待办管理器单例."""
    global _todo_manager
    if _todo_manager is None:
        _todo_manager = TodoManager()
    return _todo_manager


class TodoWriteTool(BaseTool):
    """待办事项管理工具.

    适用场景：
    - 记录代码审查待办事项
    - 跟踪 Bug 修复进度
    - 管理功能开发计划
    - 按文件组织任务清单

    特点：
    - 纯本地 JSON 存储，无网络依赖
    - 支持按文件关联待办
    - 支持优先级和标签管理
    - 适合国企内网/信创环境使用
    """

    name: str = "todo_write"
    description: str = """管理待办事项列表（Todo List）。

使用场景：
- 记录代码审查中发现的问题
- 跟踪 Bug 修复和功能开发任务
- 管理项目交付的待办清单
- 按文件组织相关的修改任务

操作说明：
- create: 创建新待办，需提供 content
- update: 更新待办，需提供 todo_id 和要更新的字段
- delete: 删除待办，需提供 todo_id
- list: 列出待办，支持按状态/优先级/文件过滤
- clear: 清空待办，可指定只清空某个文件的待办

示例：
- 创建: {"operation": "create", "content": "修复登录页面样式", "priority": "high"}
- 更新: {"operation": "update", "todo_id": "todo_abc123", "status": "done"}
- 列表: {"operation": "list", "filter_status": "todo"}
- 删除: {"operation": "delete", "todo_id": "todo_abc123"}

注意：数据存储在 ~/.claude/todos.json，适合内网环境使用。"""

    async def execute(
        self,
        operation: str = "create",
        todo_id: str | None = None,
        content: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        file_path: str | None = None,
        filter_status: str | None = None,
        filter_priority: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行待办事项操作."""
        try:
            manager = _get_todo_manager()

            if operation == "create":
                if not content:
                    return ToolResult.failure("创建待办时需要提供 content 参数")

                todo = manager.create(
                    content=content,
                    priority=priority or "medium",
                    tags=tags,
                    file_path=file_path
                )
                return ToolResult.ok(
                    f"✓ 已创建待办: {content}",
                    todo=todo,
                    todo_id=todo["id"]
                )

            elif operation == "update":
                if not todo_id:
                    return ToolResult.failure("更新待办时需要提供 todo_id 参数")

                todo = manager.update(
                    todo_id=todo_id,
                    content=content,
                    status=status,
                    priority=priority,
                    tags=tags
                )
                if todo:
                    return ToolResult.ok(
                        f"✓ 已更新待办: {todo['content']}",
                        todo=todo
                    )
                else:
                    return ToolResult.failure(f"未找到待办: {todo_id}")

            elif operation == "delete":
                if not todo_id:
                    return ToolResult.failure("删除待办时需要提供 todo_id 参数")

                if manager.delete(todo_id):
                    return ToolResult.ok(f"✓ 已删除待办: {todo_id}")
                else:
                    return ToolResult.failure(f"未找到待办: {todo_id}")

            elif operation == "list":
                todos = manager.list(
                    file_path=file_path,
                    status=filter_status,
                    priority=filter_priority
                )

                if not todos:
                    return ToolResult.ok("暂无待办事项")

                # 格式化输出
                lines = [f"待办事项列表 (共 {len(todos)} 项):", ""]

                status_icons = {
                    "todo": "⬜",
                    "in_progress": "🔄",
                    "done": "✅"
                }

                priority_icons = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢"
                }

                for todo in todos:
                    icon = status_icons.get(todo["status"], "⬜")
                    p_icon = priority_icons.get(todo["priority"], "🟡")
                    lines.append(f"{icon} {p_icon} [{todo['id']}] {todo['content']}")

                    # 显示标签
                    if todo.get("tags"):
                        lines.append(f"   🏷️ {', '.join(todo['tags'])}")

                    # 显示关联文件
                    if todo.get("file_path"):
                        lines.append(f"   📄 {todo['file_path']}")

                    lines.append("")

                # 统计
                status_count = {}
                for t in todos:
                    s = t["status"]
                    status_count[s] = status_count.get(s, 0) + 1

                summary = f"📊 统计: 待办 {status_count.get('todo', 0)} | " \
                         f"进行中 {status_count.get('in_progress', 0)} | " \
                         f"已完成 {status_count.get('done', 0)}"
                lines.append(summary)

                return ToolResult.ok(
                    "\n".join(lines),
                    todos=todos,
                    count=len(todos),
                    status_count=status_count
                )

            elif operation == "clear":
                count = manager.clear(file_path)
                if file_path:
                    return ToolResult.ok(f"✓ 已清空 {file_path} 的 {count} 项待办")
                else:
                    return ToolResult.ok(f"✓ 已清空所有 {count} 项待办")

            else:
                return ToolResult.failure(f"未知操作: {operation}")

        except Exception as e:
            return ToolResult.failure(f"待办操作失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TodoWriteParams.model_json_schema()


# 注册工具
tool_registry.register(TodoWriteTool())
