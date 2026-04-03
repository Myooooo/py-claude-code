"""TodoWriteTool 单元测试."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
import pytest

from py_claude_code.tools.todo import TodoWriteTool, TodoManager, _get_todo_manager, _todo_manager


class TestTodoManager:
    """测试 TodoManager."""

    @pytest.fixture
    def temp_todo_file(self):
        """创建临时待办文件."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('[]')
            temp_path = f.name

        # 保存原始路径
        original_home = os.environ.get('HOME')

        yield temp_path

        # 清理
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def manager(self, temp_todo_file):
        """创建测试用的 TodoManager."""
        manager = TodoManager()
        # 临时修改存储路径
        manager.storage_path = Path(temp_todo_file)
        manager._todos = []
        manager._save()
        return manager

    def test_create(self, manager):
        """测试创建待办."""
        todo = manager.create("测试待办", priority="high", tags=["test"])

        assert todo["content"] == "测试待办"
        assert todo["priority"] == "high"
        assert todo["status"] == "todo"
        assert "test" in todo["tags"]
        assert "id" in todo

    def test_update(self, manager):
        """测试更新待办."""
        todo = manager.create("原始内容")
        todo_id = todo["id"]

        updated = manager.update(todo_id, content="更新内容", status="done")

        assert updated is not None
        assert updated["content"] == "更新内容"
        assert updated["status"] == "done"

    def test_update_not_found(self, manager):
        """测试更新不存在的待办."""
        result = manager.update("non_existent_id", content="更新")
        assert result is None

    def test_delete(self, manager):
        """测试删除待办."""
        todo = manager.create("待删除")
        todo_id = todo["id"]

        assert manager.delete(todo_id) is True
        assert manager.delete(todo_id) is False  # 已删除

    def test_list(self, manager):
        """测试列出待办."""
        manager.create("待办1", priority="high")
        manager.create("待办2", priority="low", status="done")
        manager.create("待办3", priority="medium")

        all_todos = manager.list()
        assert len(all_todos) == 3

        # 按状态过滤
        done_todos = manager.list(status="done")
        assert len(done_todos) == 1

        # 按优先级过滤
        high_todos = manager.list(priority="high")
        assert len(high_todos) == 1

    def test_clear(self, manager):
        """测试清空待办."""
        manager.create("待办1")
        manager.create("待办2")

        count = manager.clear()
        assert count == 2
        assert len(manager.list()) == 0

    def test_persistence(self, manager):
        """测试持久化."""
        todo = manager.create("持久化测试")
        todo_id = todo["id"]

        # 创建新管理器实例，应能读取保存的数据
        new_manager = TodoManager()
        new_manager.storage_path = manager.storage_path
        new_manager._load()

        loaded = new_manager.list()
        assert len(loaded) == 1
        assert loaded[0]["id"] == todo_id


class TestTodoWriteTool:
    """测试 TodoWriteTool."""

    @pytest.fixture
    async def tool(self):
        """创建工具实例."""
        return TodoWriteTool()

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "todos.json"
            # 临时修改全局管理器的存储路径
            import py_claude_code.tools.todo as todo_module
            original_manager = todo_module._todo_manager

            manager = TodoManager()
            manager.storage_path = storage_path
            manager._todos = []
            manager._save()

            todo_module._todo_manager = manager

            yield storage_path

            # 恢复
            todo_module._todo_manager = original_manager

    @pytest.mark.asyncio
    async def test_create(self, temp_storage):
        """测试创建待办."""
        tool = TodoWriteTool()
        result = await tool.execute(
            operation="create",
            content="测试待办事项"
        )

        assert result.success is True
        assert "已创建待办" in result.content
        assert "todo" in result.data

    @pytest.mark.asyncio
    async def test_create_without_content(self, temp_storage):
        """测试创建待办时缺少内容."""
        tool = TodoWriteTool()
        result = await tool.execute(operation="create")

        assert result.success is False
        assert result.error is not None
        assert "需要提供 content" in str(result.error)

    @pytest.mark.asyncio
    async def test_list_empty(self, temp_storage):
        """测试空列表."""
        tool = TodoWriteTool()
        result = await tool.execute(operation="list")

        assert result.success is True
        assert "暂无待办事项" in result.content

    @pytest.mark.asyncio
    async def test_list_with_items(self, temp_storage):
        """测试列出待办."""
        tool = TodoWriteTool()

        # 创建几个待办
        await tool.execute(operation="create", content="待办1", priority="high")
        await tool.execute(operation="create", content="待办2", priority="low")

        # 列出
        result = await tool.execute(operation="list")

        assert result.success is True
        assert "待办事项列表" in result.content
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_update(self, temp_storage):
        """测试更新待办."""
        tool = TodoWriteTool()

        # 创建
        create_result = await tool.execute(
            operation="create",
            content="原始内容"
        )
        todo_id = create_result.data["todo_id"]

        # 更新
        update_result = await tool.execute(
            operation="update",
            todo_id=todo_id,
            status="done"
        )

        assert update_result.success is True
        assert "已更新" in update_result.content

    @pytest.mark.asyncio
    async def test_delete(self, temp_storage):
        """测试删除待办."""
        tool = TodoWriteTool()

        # 创建
        create_result = await tool.execute(
            operation="create",
            content="待删除"
        )
        todo_id = create_result.data["todo_id"]

        # 删除
        delete_result = await tool.execute(
            operation="delete",
            todo_id=todo_id
        )

        assert delete_result.success is True
        assert "已删除" in delete_result.content

    @pytest.mark.asyncio
    async def test_clear(self, temp_storage):
        """测试清空."""
        tool = TodoWriteTool()

        # 创建几个待办
        await tool.execute(operation="create", content="待办1")
        await tool.execute(operation="create", content="待办2")

        # 清空
        result = await tool.execute(operation="clear")

        assert result.success is True
        assert "已清空" in result.content

    @pytest.mark.asyncio
    async def test_filter_by_status(self, temp_storage):
        """测试按状态过滤."""
        tool = TodoWriteTool()

        # 创建不同状态的待办
        r1 = await tool.execute(operation="create", content="待办1")
        await tool.execute(
            operation="update",
            todo_id=r1.data["todo_id"],
            status="done"
        )
        await tool.execute(operation="create", content="待办2")

        # 过滤已完成
        result = await tool.execute(
            operation="list",
            filter_status="done"
        )

        assert result.success is True
        # 应该只显示已完成的


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
