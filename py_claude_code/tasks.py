"""任务管理系统.

支持后台异步任务执行、任务状态追踪、任务依赖管理.
适配国企内网/信创环境: 纯本地存储, 无外部依赖.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional


class TaskStatus(str, Enum):
    """任务状态."""
    PENDING = "pending"           # 等待执行
    IN_PROGRESS = "in_progress"   # 执行中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消
    STOPPED = "stopped"           # 已停止


class TaskPriority(str, Enum):
    """任务优先级."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """任务数据模型."""

    # 基本信息
    id: str
    subject: str                          # 简短标题
    description: str = ""                 # 详细描述
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM

    # 执行信息
    prompt: str = ""                      # 执行提示词/命令
    owner: Optional[str] = None           # 任务所有者(agent/subagent)

    # 依赖关系
    blocked_by: list[str] = field(default_factory=list)  # 依赖的任务ID
    blocks: list[str] = field(default_factory=list)      # 阻塞的任务ID

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # 执行结果
    output: str = ""                      # 任务输出
    error: Optional[str] = None           # 错误信息
    exit_code: Optional[int] = None       # 退出码

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "prompt": self.prompt,
            "owner": self.owner,
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """从字典创建任务."""
        return cls(
            id=data["id"],
            subject=data["subject"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "medium")),
            prompt=data.get("prompt", ""),
            owner=data.get("owner"),
            blocked_by=data.get("blocked_by", []),
            blocks=data.get("blocks", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            output=data.get("output", ""),
            error=data.get("error"),
            exit_code=data.get("exit_code"),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )

    def update_status(self, status: TaskStatus, output: str = "", error: Optional[str] = None) -> None:
        """更新任务状态."""
        self.status = status
        self.updated_at = datetime.now().isoformat()

        if status == TaskStatus.IN_PROGRESS and not self.started_at:
            self.started_at = self.updated_at

        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.CANCELLED):
            self.completed_at = self.updated_at

        if output:
            self.output = output
        if error:
            self.error = error


class TaskManager:
    """任务管理器 - 负责任务的CRUD和持久化."""

    def __init__(self) -> None:
        """初始化任务管理器."""
        self.storage_path = Path.home() / ".claude" / "tasks.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载任务."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tasks = {
                        task_id: Task.from_dict(task_data)
                        for task_id, task_data in data.items()
                    }
            except (json.JSONDecodeError, IOError, KeyError) as e:
                print(f"[TaskManager] 加载任务失败: {e}")
                self._tasks = {}
        else:
            self._tasks = {}

    def _save(self) -> None:
        """保存任务到文件."""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                data = {
                    task_id: task.to_dict()
                    for task_id, task in self._tasks.items()
                }
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[TaskManager] 保存任务失败: {e}")

    def _generate_id(self) -> str:
        """生成唯一任务ID."""
        return f"task_{uuid.uuid4().hex[:8]}"

    def create(
        self,
        subject: str,
        description: str = "",
        prompt: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        blocked_by: list[str] | None = None,
        tags: list[str] | None = None,
        owner: Optional[str] = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """创建新任务."""
        task = Task(
            id=self._generate_id(),
            subject=subject,
            description=description,
            prompt=prompt,
            priority=priority,
            blocked_by=blocked_by or [],
            tags=tags or [],
            owner=owner,
            metadata=metadata or {},
        )

        # 更新依赖关系
        for dep_id in task.blocked_by:
            if dep_id in self._tasks:
                if task.id not in self._tasks[dep_id].blocks:
                    self._tasks[dep_id].blocks.append(task.id)

        self._tasks[task.id] = task
        self._save()
        return task

    def get(self, task_id: str) -> Task | None:
        """获取任务."""
        return self._tasks.get(task_id)

    def update(
        self,
        task_id: str,
        subject: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        blocked_by: list[str] | None = None,
        tags: list[str] | None = None,
        output: str | None = None,
        error: str | None = None,
    ) -> Task | None:
        """更新任务."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if subject is not None:
            task.subject = subject
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if tags is not None:
            task.tags = tags

        # 更新依赖关系
        if blocked_by is not None:
            # 移除旧的依赖关系
            for old_dep in task.blocked_by:
                if old_dep in self._tasks and task.id in self._tasks[old_dep].blocks:
                    self._tasks[old_dep].blocks.remove(task.id)

            # 添加新的依赖关系
            task.blocked_by = blocked_by
            for dep_id in blocked_by:
                if dep_id in self._tasks:
                    if task.id not in self._tasks[dep_id].blocks:
                        self._tasks[dep_id].blocks.append(task.id)

        # 更新状态
        if status is not None:
            task.update_status(status, output or "", error)
        elif output is not None or error is not None:
            task.output = output or task.output
            task.error = error or task.error
            task.updated_at = datetime.now().isoformat()

        self._save()
        return task

    def delete(self, task_id: str) -> bool:
        """删除任务."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]

        # 清理依赖关系
        for dep_id in task.blocked_by:
            if dep_id in self._tasks and task_id in self._tasks[dep_id].blocks:
                self._tasks[dep_id].blocks.remove(task_id)

        for blocked_id in task.blocks:
            if blocked_id in self._tasks and task_id in self._tasks[blocked_id].blocked_by:
                self._tasks[blocked_id].blocked_by.remove(task_id)

        del self._tasks[task_id]
        self._save()
        return True

    def list(
        self,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> list[Task]:
        """列出任务."""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]
        if owner:
            tasks = [t for t in tasks if t.owner == owner]
        if tag:
            tasks = [t for t in tasks if tag in t.tags]

        # 按优先级和创建时间排序
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 3,
        }
        tasks.sort(key=lambda t: (
            priority_order.get(t.priority, 2),
            t.created_at
        ))

        return tasks

    def clear(self, status: TaskStatus | None = None) -> int:
        """清空任务."""
        if status:
            to_delete = [tid for tid, t in self._tasks.items() if t.status == status]
        else:
            to_delete = list(self._tasks.keys())

        for tid in to_delete:
            self.delete(tid)

        return len(to_delete)

    def get_ready_tasks(self) -> "list[Task]":
        """获取可以执行的任务（状态为pending且依赖已完成）."""
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # 检查所有依赖是否已完成
            deps_satisfied = all(
                self._tasks.get(dep_id) and
                self._tasks[dep_id].status in (TaskStatus.COMPLETED,)
                for dep_id in task.blocked_by
            )

            if deps_satisfied:
                ready.append(task)

        return ready


# 后台任务类型定义
TaskCoroutine = Callable[[], Coroutine[Any, Any, tuple[str, Optional[str], int]]]


class BackgroundTaskManager:
    """后台任务管理器 - 管理异步任务的执行."""

    def __init__(self) -> None:
        """初始化后台任务管理器."""
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._outputs: dict[str, str] = {}
        self._task_manager = TaskManager()

    async def start_task(
        self,
        task_id: str,
        coro: TaskCoroutine,
    ) -> bool:
        """启动后台任务.

        Args:
            task_id: 任务ID
            coro: 异步协程函数，返回 (output, error, exit_code)

        Returns:
            是否成功启动
        """
        if task_id in self._running_tasks:
            return False

        # 包装任务以捕获输出和状态
        async def wrapped_coro():
            try:
                output, error, exit_code = await coro()
                self._outputs[task_id] = output

                # 更新任务状态
                if exit_code == 0:
                    self._task_manager.update(
                        task_id,
                        status=TaskStatus.COMPLETED,
                        output=output,
                        error=error,
                    )
                else:
                    self._task_manager.update(
                        task_id,
                        status=TaskStatus.FAILED,
                        output=output,
                        error=error or f"Exit code: {exit_code}",
                    )

            except asyncio.CancelledError:
                self._task_manager.update(
                    task_id,
                    status=TaskStatus.STOPPED,
                    output=self._outputs.get(task_id, ""),
                    error="任务被用户停止",
                )
                raise

            except Exception as e:
                self._outputs[task_id] = self._outputs.get(task_id, "")
                self._task_manager.update(
                    task_id,
                    status=TaskStatus.FAILED,
                    output=self._outputs.get(task_id, ""),
                    error=str(e),
                )

            finally:
                if task_id in self._running_tasks:
                    del self._running_tasks[task_id]

        # 更新任务状态为执行中
        self._task_manager.update(task_id, status=TaskStatus.IN_PROGRESS)

        # 启动任务
        asyncio_task = asyncio.create_task(wrapped_coro())
        self._running_tasks[task_id] = asyncio_task

        return True

    async def stop_task(self, task_id: str) -> bool:
        """停止后台任务.

        Returns:
            是否成功停止
        """
        if task_id not in self._running_tasks:
            return False

        task = self._running_tasks[task_id]
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        return True

    def get_output(self, task_id: str) -> str:
        """获取任务当前输出."""
        return self._outputs.get(task_id, "")

    def is_running(self, task_id: str) -> bool:
        """检查任务是否在运行中."""
        if task_id not in self._running_tasks:
            return False

        task = self._running_tasks[task_id]
        return not task.done()

    def list_running(self) -> list[str]:
        """列出所有运行中的任务ID."""
        return [
            task_id for task_id, task in self._running_tasks.items()
            if not task.done()
        ]

    async def wait_for_task(self, task_id: str, timeout: float | None = None) -> bool:
        """等待任务完成.

        Returns:
            是否在超时前完成
        """
        if task_id not in self._running_tasks:
            return True

        task = self._running_tasks[task_id]

        try:
            await asyncio.wait_for(task, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_for_all(self, timeout: float | None = None) -> None:
        """等待所有任务完成."""
        if not self._running_tasks:
            return

        tasks = list(self._running_tasks.values())

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            pass


# 全局实例
_task_manager: TaskManager | None = None
_background_manager: BackgroundTaskManager | None = None


def get_task_manager() -> TaskManager:
    """获取任务管理器单例."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def get_background_manager() -> BackgroundTaskManager:
    """获取后台任务管理器单例."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager
