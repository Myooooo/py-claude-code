"""任务管理工具单元测试."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
import pytest

from py_claude_code.tasks import (
    Task,
    TaskStatus,
    TaskPriority,
    TaskManager,
    BackgroundTaskManager,
    get_task_manager,
    get_background_manager,
)
from py_claude_code.tools.tasks import (
    TaskCreateTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskListTool,
    TaskStopTool,
    TaskOutputTool,
)


class TestTaskManager:
    """测试 TaskManager."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            # 临时替换存储路径
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            # 恢复
            core_tasks._task_manager = original_manager

    def test_create_task(self, temp_storage):
        """测试创建任务."""
        manager = temp_storage

        task = manager.create(
            subject="测试任务",
            description="这是一个测试",
            priority=TaskPriority.HIGH,
            tags=["test", "dev"],
        )

        assert task.subject == "测试任务"
        assert task.description == "这是一个测试"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
        assert "test" in task.tags
        assert task.id.startswith("task_")

    def test_get_task(self, temp_storage):
        """测试获取任务."""
        manager = temp_storage

        created = manager.create(subject="获取测试")
        fetched = manager.get(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.subject == "获取测试"

    def test_get_nonexistent(self, temp_storage):
        """测试获取不存在的任务."""
        manager = temp_storage

        result = manager.get("task_nonexistent")
        assert result is None

    def test_update_task(self, temp_storage):
        """测试更新任务."""
        manager = temp_storage

        task = manager.create(subject="原始标题")

        updated = manager.update(
            task.id,
            subject="新标题",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.CRITICAL,
        )

        assert updated is not None
        assert updated.subject == "新标题"
        assert updated.status == TaskStatus.IN_PROGRESS
        assert updated.priority == TaskPriority.CRITICAL

    def test_delete_task(self, temp_storage):
        """测试删除任务."""
        manager = temp_storage

        task = manager.create(subject="待删除")
        task_id = task.id

        assert manager.delete(task_id) is True
        assert manager.get(task_id) is None
        assert manager.delete(task_id) is False

    def test_list_tasks(self, temp_storage):
        """测试列出任务."""
        manager = temp_storage

        # 创建多个任务
        manager.create(subject="任务1", priority=TaskPriority.HIGH)
        manager.create(subject="任务2", priority=TaskPriority.LOW)
        manager.create(subject="任务3", priority=TaskPriority.MEDIUM)

        all_tasks = manager.list()
        assert len(all_tasks) == 3

        # 按优先级过滤
        high_tasks = manager.list(priority=TaskPriority.HIGH)
        assert len(high_tasks) == 1

    def test_task_dependencies(self, temp_storage):
        """测试任务依赖."""
        manager = temp_storage

        # 创建依赖任务
        task1 = manager.create(subject="前置任务")
        task2 = manager.create(
            subject="后续任务",
            blocked_by=[task1.id],
        )

        assert task2.blocked_by == [task1.id]
        assert task2.id in task1.blocks

        # 删除前置任务
        manager.delete(task1.id)

        # 后续任务的依赖应该被清理
        task2_after = manager.get(task2.id)
        assert task1.id not in task2_after.blocked_by

    def test_persistence(self, temp_storage):
        """测试持久化."""
        manager = temp_storage

        task = manager.create(subject="持久化测试")
        task_id = task.id

        # 创建新管理器实例
        new_manager = TaskManager()
        new_manager.storage_path = manager.storage_path
        new_manager._load()

        loaded = new_manager.get(task_id)
        assert loaded is not None
        assert loaded.subject == "持久化测试"


class TestBackgroundTaskManager:
    """测试 BackgroundTaskManager."""

    @pytest.fixture
    def bg_manager(self):
        """创建后台管理器."""
        return BackgroundTaskManager()

    @pytest.mark.asyncio
    async def test_start_and_stop_task(self, bg_manager):
        """测试启动和停止任务."""

        async def sample_task():
            await asyncio.sleep(0.1)
            return "完成", None, 0

        # 启动任务
        success = await bg_manager.start_task("task_test", sample_task)
        assert success is True

        # 检查是否运行中
        assert bg_manager.is_running("task_test") is True

        # 等待任务完成或停止
        await bg_manager.stop_task("task_test")

        # 等待一小段时间
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_task_output(self, bg_manager):
        """测试任务输出."""

        async def output_task():
            return "任务输出内容", None, 0

        await bg_manager.start_task("task_output", output_task)
        await asyncio.sleep(0.05)

        output = bg_manager.get_output("task_output")
        assert output == "任务输出内容"

    @pytest.mark.asyncio
    async def test_list_running(self, bg_manager):
        """测试列出运行中任务."""

        async def long_task():
            await asyncio.sleep(10)
            return "", None, 0

        # 启动多个任务
        await bg_manager.start_task("task_1", long_task)
        await bg_manager.start_task("task_2", long_task)

        running = bg_manager.list_running()
        assert len(running) == 2

        # 停止所有
        await bg_manager.stop_task("task_1")
        await bg_manager.stop_task("task_2")


class TestTaskCreateTool:
    """测试 TaskCreateTool."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            core_tasks._task_manager = original_manager

    @pytest.mark.asyncio
    async def test_create_simple_task(self, temp_storage):
        """测试创建简单任务."""
        tool = TaskCreateTool()

        result = await tool.execute(
            subject="简单任务",
            description="这是一个简单任务",
        )

        assert result.success is True
        assert "已创建任务" in result.content
        assert "task_" in result.data["task_id"]

    @pytest.mark.asyncio
    async def test_create_with_priority(self, temp_storage):
        """测试创建带优先级的任务."""
        tool = TaskCreateTool()

        result = await tool.execute(
            subject="高优先级任务",
            priority="high",
            tags=["urgent", "dev"],
        )

        assert result.success is True
        task = result.data["task"]
        assert task["priority"] == "high"
        assert "urgent" in task["tags"]


class TestTaskGetTool:
    """测试 TaskGetTool."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            core_tasks._task_manager = original_manager

    @pytest.mark.asyncio
    async def test_get_existing_task(self, temp_storage):
        """测试获取存在的任务."""
        tool_create = TaskCreateTool()
        tool_get = TaskGetTool()

        # 先创建任务
        created = await tool_create.execute(subject="获取测试")
        task_id = created.data["task_id"]

        # 再获取
        result = await tool_get.execute(task_id=task_id)

        assert result.success is True
        assert "获取测试" in result.content
        assert result.data["task"]["subject"] == "获取测试"

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, temp_storage):
        """测试获取不存在的任务."""
        tool = TaskGetTool()

        result = await tool.execute(task_id="task_nonexistent")

        assert result.success is False
        assert "未找到任务" in result.error


class TestTaskUpdateTool:
    """测试 TaskUpdateTool."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            core_tasks._task_manager = original_manager

    @pytest.mark.asyncio
    async def test_update_status(self, temp_storage):
        """测试更新任务状态."""
        tool_create = TaskCreateTool()
        tool_update = TaskUpdateTool()

        created = await tool_create.execute(subject="状态测试")
        task_id = created.data["task_id"]

        result = await tool_update.execute(
            task_id=task_id,
            status="completed",
        )

        assert result.success is True
        assert result.data["task"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_priority(self, temp_storage):
        """测试更新优先级."""
        tool_create = TaskCreateTool()
        tool_update = TaskUpdateTool()

        created = await tool_create.execute(subject="优先级测试")
        task_id = created.data["task_id"]

        result = await tool_update.execute(
            task_id=task_id,
            priority="critical",
        )

        assert result.success is True
        assert result.data["task"]["priority"] == "critical"


class TestTaskListTool:
    """测试 TaskListTool."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            core_tasks._task_manager = original_manager

    @pytest.mark.asyncio
    async def test_list_empty(self, temp_storage):
        """测试空列表."""
        tool = TaskListTool()

        result = await tool.execute()

        assert result.success is True
        assert "暂无任务" in result.content

    @pytest.mark.asyncio
    async def test_list_with_tasks(self, temp_storage):
        """测试列出任务."""
        tool_create = TaskCreateTool()
        tool_list = TaskListTool()

        # 创建多个任务
        await tool_create.execute(subject="任务1")
        await tool_create.execute(subject="任务2")

        result = await tool_list.execute()

        assert result.success is True
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, temp_storage):
        """测试按状态过滤."""
        tool_create = TaskCreateTool()
        tool_update = TaskUpdateTool()
        tool_list = TaskListTool()

        # 创建并更新状态
        created1 = await tool_create.execute(subject="已完成")
        await tool_update.execute(
            task_id=created1.data["task_id"],
            status="completed",
        )

        await tool_create.execute(subject="待办")

        # 过滤
        result = await tool_list.execute(status="completed")

        assert result.success is True
        assert result.data["count"] == 1


class TestTaskOutputTool:
    """测试 TaskOutputTool."""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tasks.json"
            import py_claude_code.tasks as core_tasks
            original_manager = core_tasks._task_manager

            manager = TaskManager()
            manager.storage_path = storage_path
            manager._tasks = {}

            core_tasks._task_manager = manager

            yield manager

            core_tasks._task_manager = original_manager

    @pytest.mark.asyncio
    async def test_get_output(self, temp_storage):
        """测试获取任务输出."""
        tool_create = TaskCreateTool()
        tool_update = TaskUpdateTool()
        tool_output = TaskOutputTool()

        # 创建并设置输出
        created = await tool_create.execute(subject="输出测试")
        task_id = created.data["task_id"]

        await tool_update.execute(
            task_id=task_id,
            output="这是任务输出内容",
            status="completed",
        )

        result = await tool_output.execute(task_id=task_id)

        assert result.success is True
        assert "这是任务输出内容" in result.content

    @pytest.mark.asyncio
    async def test_pagination(self, temp_storage):
        """测试分页."""
        tool_create = TaskCreateTool()
        tool_update = TaskUpdateTool()
        tool_output = TaskOutputTool()

        created = await tool_create.execute(subject="分页测试")
        task_id = created.data["task_id"]

        # 设置大输出
        large_output = "A" * 20000
        await tool_update.execute(
            task_id=task_id,
            output=large_output,
            status="completed",
        )

        # 获取第一页
        result = await tool_output.execute(task_id=task_id, offset=0, limit=5000)

        assert result.success is True
        assert result.data["has_more"] is True
        assert result.data["total_length"] == 20000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
