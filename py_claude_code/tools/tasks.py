"""任务管理工具集.

提供任务的创建、查询、更新、停止、获取输出等功能.
适配国企内网/信创环境: 纯本地存储, 无外部依赖.
"""

from typing import Any, Literal
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry
from ..tasks import (
    get_task_manager,
    get_background_manager,
    TaskManager,
    BackgroundTaskManager,
    Task,
    TaskStatus,
    TaskPriority,
)


class TaskCreateParams(ToolParameters):
    """任务创建参数."""

    subject: str = Field(..., description="任务标题/主题")
    description: str = Field(default="", description="任务详细描述")
    prompt: str = Field(default="", description="执行提示词或命令")
    priority: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description="任务优先级"
    )
    blocked_by: list[str] = Field(
        default_factory=list,
        description="依赖的任务ID列表"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="标签列表"
    )
    owner: str | None = Field(
        default=None,
        description="任务所有者(agent/subagent)"
    )

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        """验证标题不为空."""
        if not v or not v.strip():
            raise ValueError("任务标题不能为空")
        return v.strip()


class TaskGetParams(ToolParameters):
    """任务获取参数."""

    task_id: str = Field(..., description="任务ID")


class TaskUpdateParams(ToolParameters):
    """任务更新参数."""

    task_id: str = Field(..., description="任务ID")
    subject: str | None = Field(default=None, description="新标题")
    description: str | None = Field(default=None, description="新描述")
    status: Literal["pending", "in_progress", "completed", "failed", "cancelled", "stopped"] | None = Field(
        default=None,
        description="新状态"
    )
    priority: Literal["low", "medium", "high", "critical"] | None = Field(
        default=None,
        description="新优先级"
    )
    blocked_by: list[str] | None = Field(
        default=None,
        description="新的依赖任务ID列表"
    )
    tags: list[str] | None = Field(
        default=None,
        description="新标签列表"
    )
    output: str | None = Field(
        default=None,
        description="任务输出内容(用于手动更新)"
    )
    error: str | None = Field(
        default=None,
        description="错误信息"
    )


class TaskListParams(ToolParameters):
    """任务列表参数."""

    status: Literal["pending", "in_progress", "completed", "failed", "cancelled", "stopped", "all"] | None = Field(
        default=None,
        description="按状态过滤"
    )
    priority: Literal["low", "medium", "high", "critical", "all"] | None = Field(
        default=None,
        description="按优先级过滤"
    )
    owner: str | None = Field(
        default=None,
        description="按所有者过滤"
    )
    tag: str | None = Field(
        default=None,
        description="按标签过滤"
    )


class TaskStopParams(ToolParameters):
    """任务停止参数."""

    task_id: str = Field(..., description="要停止的任务ID")


class TaskOutputParams(ToolParameters):
    """任务输出参数."""

    task_id: str = Field(..., description="任务ID")
    offset: int = Field(
        default=0,
        description="输出偏移量(字符)",
        ge=0
    )
    limit: int = Field(
        default=10000,
        description="最大返回字符数",
        ge=100,
        le=50000
    )


def _format_task(task: Task, detailed: bool = False) -> str:
    """格式化任务为可读字符串."""
    status_icons = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.IN_PROGRESS: "🔄",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.CANCELLED: "🚫",
        TaskStatus.STOPPED: "⏹️",
    }

    priority_icons = {
        TaskPriority.CRITICAL: "🔴",
        TaskPriority.HIGH: "🟠",
        TaskPriority.MEDIUM: "🟡",
        TaskPriority.LOW: "🟢",
    }

    icon = status_icons.get(task.status, "⏳")
    p_icon = priority_icons.get(task.priority, "🟡")

    lines = [f"{icon} {p_icon} [{task.id}] {task.subject}"]

    if detailed:
        if task.description:
            lines.append(f"   描述: {task.description}")

        lines.append(f"   状态: {task.status.value}")
        lines.append(f"   优先级: {task.priority.value}")

        if task.owner:
            lines.append(f"   所有者: {task.owner}")

        if task.tags:
            lines.append(f"   标签: {', '.join(task.tags)}")

        if task.blocked_by:
            lines.append(f"   依赖于: {', '.join(task.blocked_by)}")

        if task.blocks:
            lines.append(f"   阻塞: {', '.join(task.blocks)}")

        lines.append(f"   创建: {task.created_at}")

        if task.started_at:
            lines.append(f"   开始: {task.started_at}")

        if task.completed_at:
            lines.append(f"   完成: {task.completed_at}")

        if task.error:
            lines.append(f"   错误: {task.error}")

    return "\n".join(lines)


class TaskCreateTool(BaseTool):
    """创建任务工具."""

    name: str = "task_create"
    description: str = """创建新任务。

使用场景：
- 创建需要后台执行的长期任务
- 记录需要跟踪的工作项
- 建立任务依赖关系
- 分配给子Agent处理

任务状态流转：
  pending → in_progress → completed/failed/stopped

示例：
- 简单任务: {"subject": "分析代码", "description": "分析main.py的代码结构"}
- 带优先级: {"subject": "修复Bug", "priority": "high", "tags": ["bug", "urgent"]}
- 带依赖: {"subject": "部署", "blocked_by": ["task_xxx"], "prompt": "执行部署脚本"}

注意：任务数据存储在 ~/.claude/tasks.json"""

    async def execute(
        self,
        subject: str,
        description: str = "",
        prompt: str = "",
        priority: str = "medium",
        blocked_by: list[str] | None = None,
        tags: list[str] | None = None,
        owner: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行创建任务."""
        try:
            manager = get_task_manager()

            # 转换优先级
            try:
                task_priority = TaskPriority(priority)
            except ValueError:
                task_priority = TaskPriority.MEDIUM

            task = manager.create(
                subject=subject,
                description=description,
                prompt=prompt,
                priority=task_priority,
                blocked_by=blocked_by or [],
                tags=tags or [],
                owner=owner,
            )

            return ToolResult.ok(
                f"✅ 已创建任务 [{task.id}]: {task.subject}",
                task=task.to_dict(),
                task_id=task.id,
            )

        except Exception as e:
            return ToolResult.failure(f"创建任务失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskCreateParams.model_json_schema()


class TaskGetTool(BaseTool):
    """获取任务详情工具."""

    name: str = "task_get"
    description: str = """获取任务的详细信息。

使用场景：
- 查询特定任务的完整信息
- 检查任务状态和输出
- 查看任务依赖关系

示例：
- 获取任务: {"task_id": "task_abc123"}"""

    async def execute(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:
        """执行获取任务."""
        try:
            manager = get_task_manager()
            task = manager.get(task_id)

            if not task:
                return ToolResult.failure(f"未找到任务: {task_id}")

            # 获取当前输出（如果是运行中的任务）
            bg_manager = get_background_manager()
            current_output = bg_manager.get_output(task_id)
            if current_output:
                task.output = current_output

            formatted = _format_task(task, detailed=True)

            return ToolResult.ok(
                formatted,
                task=task.to_dict(),
                is_running=bg_manager.is_running(task_id),
            )

        except Exception as e:
            return ToolResult.failure(f"获取任务失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskGetParams.model_json_schema()


class TaskUpdateTool(BaseTool):
    """更新任务工具."""

    name: str = "task_update"
    description: str = """更新任务的属性。

使用场景：
- 修改任务标题/描述
- 更新任务状态
- 更改优先级
- 修改依赖关系
- 添加输出内容

示例：
- 更新状态: {"task_id": "task_xxx", "status": "completed"}
- 更新优先级: {"task_id": "task_xxx", "priority": "high"}
- 更新依赖: {"task_id": "task_xxx", "blocked_by": ["task_yyy"]}
- 添加输出: {"task_id": "task_xxx", "output": "任务执行结果..."}"""

    async def execute(
        self,
        task_id: str,
        subject: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        blocked_by: list[str] | None = None,
        tags: list[str] | None = None,
        output: str | None = None,
        error: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行更新任务."""
        try:
            manager = get_task_manager()

            # 转换状态
            task_status = None
            if status:
                try:
                    task_status = TaskStatus(status)
                except ValueError:
                    return ToolResult.failure(f"无效的状态值: {status}")

            # 转换优先级
            task_priority = None
            if priority:
                try:
                    task_priority = TaskPriority(priority)
                except ValueError:
                    return ToolResult.failure(f"无效的优先级值: {priority}")

            task = manager.update(
                task_id=task_id,
                subject=subject,
                description=description,
                status=task_status,
                priority=task_priority,
                blocked_by=blocked_by,
                tags=tags,
                output=output,
                error=error,
            )

            if not task:
                return ToolResult.failure(f"未找到任务: {task_id}")

            return ToolResult.ok(
                f"✅ 已更新任务 [{task.id}]: {task.subject}",
                task=task.to_dict(),
            )

        except Exception as e:
            return ToolResult.failure(f"更新任务失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskUpdateParams.model_json_schema()


class TaskListTool(BaseTool):
    """列出任务工具."""

    name: str = "task_list"
    description: str = """列出所有任务，支持多种过滤条件。

使用场景：
- 查看所有待办任务
- 按状态筛选任务
- 按优先级筛选任务
- 查看分配给特定Agent的任务

示例：
- 列出所有: {}
- 待办任务: {"status": "pending"}
- 高优先级: {"priority": "high"}
- 进行中: {"status": "in_progress"}
- 按标签: {"tag": "bug"}

状态值: pending, in_progress, completed, failed, cancelled, stopped
优先级: low, medium, high, critical"""

    async def execute(
        self,
        status: str | None = None,
        priority: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行列出任务."""
        try:
            manager = get_task_manager()
            bg_manager = get_background_manager()

            # 转换过滤参数
            task_status = None
            if status and status != "all":
                try:
                    task_status = TaskStatus(status)
                except ValueError:
                    return ToolResult.failure(f"无效的状态值: {status}")

            task_priority = None
            if priority and priority != "all":
                try:
                    task_priority = TaskPriority(priority)
                except ValueError:
                    return ToolResult.failure(f"无效的优先级值: {priority}")

            tasks = manager.list(
                status=task_status,
                priority=task_priority,
                owner=owner,
                tag=tag,
            )

            if not tasks:
                return ToolResult.ok("📋 暂无任务")

            # 格式化输出
            lines = [f"📋 任务列表 (共 {len(tasks)} 项):", ""]

            status_count = {}
            for task in tasks:
                status_count[task.status.value] = status_count.get(task.status.value, 0) + 1
                lines.append(_format_task(task, detailed=False))

            # 统计
            lines.append("")
            summary_parts = []
            for status_val, count in sorted(status_count.items()):
                summary_parts.append(f"{status_val}: {count}")
            lines.append(f"📊 统计: {' | '.join(summary_parts)}")

            return ToolResult.ok(
                "\n".join(lines),
                tasks=[t.to_dict() for t in tasks],
                count=len(tasks),
                status_count=status_count,
            )

        except Exception as e:
            return ToolResult.failure(f"列出任务失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskListParams.model_json_schema()


class TaskStopTool(BaseTool):
    """停止任务工具."""

    name: str = "task_stop"
    description: str = """停止正在执行的后台任务。

使用场景：
- 取消正在运行的长时间任务
- 停止不需要的任务执行
- 终止卡住的任务

注意：
- 只能停止状态为 in_progress 的任务
- 已完成的任务无法停止

示例：
- 停止任务: {"task_id": "task_xxx"}"""

    async def execute(
        self,
        task_id: str,
        **kwargs: Any
    ) -> ToolResult:
        """执行停止任务."""
        try:
            manager = get_task_manager()
            bg_manager = get_background_manager()

            task = manager.get(task_id)
            if not task:
                return ToolResult.failure(f"未找到任务: {task_id}")

            if task.status != TaskStatus.IN_PROGRESS:
                return ToolResult.failure(
                    f"任务 [{task_id}] 当前状态为 {task.status.value}，无法停止"
                )

            # 停止后台执行
            success = await bg_manager.stop_task(task_id)

            if success:
                return ToolResult.ok(
                    f"⏹️ 已停止任务 [{task_id}]: {task.subject}",
                    task_id=task_id,
                )
            else:
                return ToolResult.failure(f"停止任务失败: {task_id}")

        except Exception as e:
            return ToolResult.failure(f"停止任务失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskStopParams.model_json_schema()


class TaskOutputTool(BaseTool):
    """获取任务输出工具."""

    name: str = "task_output"
    description: str = """获取任务的输出内容。

使用场景：
- 查看任务的执行结果
- 获取后台任务的输出
- 查看错误信息

特点：
- 支持分页获取大输出
- 实时获取运行中任务的输出
- 支持偏移量和长度限制

示例：
- 获取输出: {"task_id": "task_xxx"}
- 分页获取: {"task_id": "task_xxx", "offset": 0, "limit": 5000}
- 获取最新: {"task_id": "task_xxx", "offset": 10000}"""

    async def execute(
        self,
        task_id: str,
        offset: int = 0,
        limit: int = 10000,
        **kwargs: Any
    ) -> ToolResult:
        """执行获取任务输出."""
        try:
            manager = get_task_manager()
            bg_manager = get_background_manager()

            task = manager.get(task_id)
            if not task:
                return ToolResult.failure(f"未找到任务: {task_id}")

            # 获取输出（优先从后台管理器获取实时输出）
            output = bg_manager.get_output(task_id) or task.output

            # 分页
            total_length = len(output)
            if offset >= total_length:
                return ToolResult.ok(
                    "(无输出)",
                    task_id=task_id,
                    offset=offset,
                    total_length=total_length,
                )

            paginated_output = output[offset:offset + limit]
            has_more = (offset + limit) < total_length

            result_lines = [
                f"📄 任务 [{task_id}] 输出:",
                f"状态: {task.status.value}",
                f"长度: {offset + len(paginated_output)} / {total_length} 字符",
                "",
                "--- 输出开始 ---",
                paginated_output,
                "--- 输出结束 ---",
            ]

            if has_more:
                result_lines.append(f"\n(还有 {total_length - offset - limit} 字符，使用 offset={offset + limit} 获取)")

            if task.error:
                result_lines.extend([
                    "",
                    f"❌ 错误: {task.error}",
                ])

            return ToolResult.ok(
                "\n".join(result_lines),
                task_id=task_id,
                status=task.status.value,
                output=output,
                error=task.error,
                offset=offset,
                limit=limit,
                total_length=total_length,
                has_more=has_more,
                is_running=bg_manager.is_running(task_id),
            )

        except Exception as e:
            return ToolResult.failure(f"获取任务输出失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return TaskOutputParams.model_json_schema()


# 注册工具
tool_registry.register(TaskCreateTool())
tool_registry.register(TaskGetTool())
tool_registry.register(TaskUpdateTool())
tool_registry.register(TaskListTool())
tool_registry.register(TaskStopTool())
tool_registry.register(TaskOutputTool())
