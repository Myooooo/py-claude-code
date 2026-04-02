"""文件操作工具."""

import os
from pathlib import Path
from typing import Any, ClassVar, Literal
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry


class FileReadParams(ToolParameters):
    """文件读取参数."""

    file_path: str = Field(..., description="要读取的文件路径")
    offset: int = Field(default=1, description="起始行号（从1开始）")
    limit: int | None = Field(default=None, description="读取行数限制，None表示读取全部")

    # 大文件保护阈值
    MAX_FILE_SIZE_MB: int = 50  # 50MB
    SAFE_READ_LIMIT: int = 5000  # 安全读取行数限制

    @field_validator("file_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """验证路径不为空."""
        if not v or not v.strip():
            raise ValueError("文件路径不能为空")
        return v.strip()

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        """验证offset至少为1."""
        if v < 1:
            raise ValueError("offset 必须 >= 1")
        return v


class FileWriteParams(ToolParameters):
    """文件写入参数."""

    file_path: str = Field(..., description="要写入的文件路径")
    content: str = Field(..., description="文件内容")

    @field_validator("file_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """验证路径不为空."""
        if not v or not v.strip():
            raise ValueError("文件路径不能为空")
        return v.strip()


class FileEditParams(ToolParameters):
    """文件编辑参数."""

    file_path: str = Field(..., description="要编辑的文件路径")
    old_string: str = Field(..., description="要替换的旧字符串")
    new_string: str = Field(..., description="替换后的新字符串")
    replace_all: bool = Field(
        default=False,
        description="是否替换所有匹配项，默认只替换第一个"
    )

    @field_validator("file_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """验证路径不为空."""
        if not v or not v.strip():
            raise ValueError("文件路径不能为空")
        return v.strip()


class ViewParams(ToolParameters):
    """目录查看参数."""

    path: str = Field(default=".", description="要查看的路径")
    depth: int = Field(default=2, description="递归深度")

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: int) -> int:
        """验证depth在有效范围内."""
        if v < 0:
            raise ValueError("depth 必须 >= 0")
        if v > 5:
            raise ValueError("depth 最大为 5")
        return v


class FileReadTool(BaseTool):
    """文件读取工具."""

    name: str = "file_read"
    description: str = """读取指定文件的内容。
使用场景：查看文件内容、读取配置文件、查看代码等。
注意：
- 对于大文件，建议指定 offset 和 limit 分批读取
- 文件路径可以是相对路径或绝对路径
- 如果不指定 limit，将读取整个文件（可能占用大量token）
- 超过50MB的文件会被拒绝读取，需要分批处理
- 超过1MB的文件会自动限制读取前5000行"""

    async def execute(
        self,
        file_path: str,
        offset: int = 1,
        limit: int | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行文件读取."""
        try:
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                return ToolResult.error(f"文件不存在: {file_path}")

            if not path.is_file():
                return ToolResult.error(f"路径不是文件: {file_path}")

            # 大文件保护检查
            file_size = path.stat().st_size
            max_size = FileReadParams.MAX_FILE_SIZE_MB * 1024 * 1024

            if file_size > max_size:
                return ToolResult.error(
                    f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，超过安全限制 "
                    f"({FileReadParams.MAX_FILE_SIZE_MB}MB)。"
                    f"建议使用 offset 和 limit 参数分批读取。",
                    file_path=str(path),
                    file_size_bytes=file_size,
                )

            # 如果没有指定limit，使用安全限制
            effective_limit = limit
            if effective_limit is None and file_size > 1024 * 1024:  # >1MB的文件
                effective_limit = FileReadParams.SAFE_READ_LIMIT
                warning_msg = f"⚠️ 文件较大，自动限制读取前 {effective_limit} 行。"
            else:
                warning_msg = None

            # 使用逐行读取避免内存问题
            lines: list[str] = []
            total_lines = 0

            with open(path, "r", encoding="utf-8") as f:
                # 跳过前 offset-1 行
                for _ in range(offset - 1):
                    try:
                        next(f)
                        total_lines += 1
                    except StopIteration:
                        return ToolResult.error(f"offset {offset} 超出文件行数范围")

                # 读取指定行数
                remaining = effective_limit if effective_limit else None
                for line in f:
                    total_lines += 1
                    if remaining is not None and len(lines) >= remaining:
                        # 继续计数但不读取
                        continue
                    # 去掉行尾换行符
                    lines.append(line.rstrip('\n\r'))

            # 添加行号
            numbered_lines = []
            for i, line in enumerate(lines, start=offset):
                numbered_lines.append(f"{i:4d} | {line}")

            result_content = "\n".join(numbered_lines)
            if warning_msg:
                result_content = f"{warning_msg}\n\n{result_content}"

            return ToolResult.ok(
                result_content,
                file_path=str(path),
                total_lines=total_lines,
                shown_lines=len(lines),
                start_line=offset,
                end_line=offset + len(lines) - 1,
                truncated=(effective_limit is not None and total_lines > len(lines)),
            )

        except UnicodeDecodeError:
            return ToolResult.error(f"无法以UTF-8编码读取文件: {file_path}")
        except PermissionError:
            return ToolResult.error(f"无权限读取文件: {file_path}")
        except Exception as e:
            return ToolResult.error(f"读取文件失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return FileReadParams.model_json_schema()


class FileWriteTool(BaseTool):
    """文件写入工具."""

    name: str = "file_write"
    description: str = """创建新文件或覆盖写入已有文件。
使用场景：创建新文件、生成代码、写入配置等。
警告：
- 如果文件已存在，将会被覆盖
- 对于已有文件的修改，建议使用 file_edit 工具
- 会自动创建不存在的父目录"""

    async def execute(
        self,
        file_path: str,
        content: str,
        **kwargs: Any
    ) -> ToolResult:
        """执行文件写入."""
        try:
            path = Path(file_path).expanduser().resolve()

            # 确保父目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            # 检查是否是覆盖操作
            existed = path.exists()

            # 写入文件
            path.write_text(content, encoding="utf-8")

            action = "覆盖" if existed else "创建"
            return ToolResult.ok(
                f"成功{action}文件: {path}",
                file_path=str(path),
                bytes_written=len(content.encode("utf-8")),
                existed=existed,
            )

        except PermissionError:
            return ToolResult.error(f"无权限写入文件: {file_path}")
        except Exception as e:
            return ToolResult.error(f"写入文件失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return FileWriteParams.model_json_schema()


class FileEditTool(BaseTool):
    """文件编辑工具."""

    name: str = "file_edit"
    description: str = """编辑已有文件，替换指定内容。
使用场景：修改代码、更新配置、修复bug等。
注意：
- old_string 必须是文件中存在的完整内容
- old_string 和 new_string 都必须准确无误
- 默认只替换第一个匹配项（安全模式）
- 如需替换所有匹配，请设置 replace_all=true
- 如果不确定文件内容，先使用 file_read 查看"""

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any
    ) -> ToolResult:
        """执行文件编辑."""
        try:
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                return ToolResult.error(f"文件不存在: {file_path}")

            if not path.is_file():
                return ToolResult.error(f"路径不是文件: {file_path}")

            # 读取文件内容
            content = path.read_text(encoding="utf-8")

            # 检查old_string是否存在
            if old_string not in content:
                return ToolResult.error(
                    f"未找到要替换的内容。请确保 old_string 与文件中的内容完全匹配。",
                    file_path=str(path),
                )

            # 统计匹配次数
            match_count = content.count(old_string)

            # 根据replace_all参数决定替换策略
            if replace_all:
                # 替换所有匹配
                new_content = content.replace(old_string, new_string)
                replacements = match_count
                warning_msg = None
            else:
                # 只替换第一个匹配
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1

                # 如果有多处匹配，给出警告
                if match_count > 1:
                    warning_msg = (
                        f"⚠️ 警告：文件中有 {match_count} 处匹配，"
                        f"仅替换了第1处。如需替换所有，请设置 replace_all=true。"
                    )
                else:
                    warning_msg = None

            # 写入文件
            path.write_text(new_content, encoding="utf-8")

            result_message = f"成功编辑文件，替换了 {replacements} 处内容"
            if warning_msg:
                result_message = f"{warning_msg}\n\n{result_message}"

            return ToolResult.ok(
                result_message,
                file_path=str(path),
                replacements=replacements,
                total_matches=match_count,
                replace_all=replace_all,
                original_size=len(content),
                new_size=len(new_content),
            )

        except PermissionError:
            return ToolResult.error(f"无权限编辑文件: {file_path}")
        except Exception as e:
            return ToolResult.error(f"编辑文件失败: {e}")

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return FileEditParams.model_json_schema()


class ViewTool(BaseTool):
    """目录查看工具."""

    name: str = "view"
    description: str = """查看目录结构和文件列表。
使用场景：探索项目结构、查找文件、了解目录内容等。
注意：
- depth 控制递归深度，默认为 2
- 深度过大可能产生大量输出
- 会自动跳过常见的忽略目录（如 .git, node_modules）"""

    IGNORE_DIRS: ClassVar[set[str]] = {
        ".git", "__pycache__", ".pytest_cache", "node_modules",
        ".venv", "venv", ".env", "dist", "build", ".tox",
        ".idea", ".vscode", ".vs", "target", ".claude"
    }

    async def execute(
        self,
        path: str = ".",
        depth: int = 2,
        **kwargs: Any
    ) -> ToolResult:
        """执行目录查看."""
        try:
            base_path = Path(path).expanduser().resolve()

            if not base_path.exists():
                return ToolResult.error(f"路径不存在: {path}")

            if base_path.is_file():
                # 如果是文件，显示文件信息
                stat = base_path.stat()
                info = f"文件: {base_path}\n"
                info += f"大小: {stat.st_size} bytes\n"
                info += f"修改时间: {stat.st_mtime}"
                return ToolResult.ok(info, file_path=str(base_path))

            # 构建目录树
            lines = [str(base_path)]
            self._build_tree(base_path, lines, "", depth, 0)

            return ToolResult.ok(
                "\n".join(lines),
                path=str(base_path),
                depth=depth,
            )

        except PermissionError:
            return ToolResult.error(f"无权限访问路径: {path}")
        except Exception as e:
            return ToolResult.error(f"查看目录失败: {e}")

    def _build_tree(
        self,
        path: Path,
        lines: list[str],
        prefix: str,
        max_depth: int,
        current_depth: int
    ) -> None:
        """递归构建目录树."""
        if current_depth >= max_depth:
            return

        try:
            entries = list(path.iterdir())
        except PermissionError:
            lines.append(f"{prefix}└── [无权限访问]")
            return

        # 排序：目录在前，文件在后
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

        # 过滤忽略目录
        entries = [
            e for e in entries
            if e.name not in self.IGNORE_DIRS and not e.name.startswith(".")
        ]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._build_tree(
                    entry, lines, prefix + extension, max_depth, current_depth + 1
                )

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return ViewParams.model_json_schema()


# 注册工具
tool_registry.register(FileReadTool())
tool_registry.register(FileWriteTool())
tool_registry.register(FileEditTool())
tool_registry.register(ViewTool())
