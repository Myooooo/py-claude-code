"""搜索工具（glob和grep）."""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, ClassVar
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry


class GlobParams(ToolParameters):
    """文件匹配搜索参数."""

    pattern: str = Field(..., description="glob匹配模式，如 '*.py' 或 '**/*.js'")
    path: str = Field(default=".", description="搜索目录")
    max_depth: int = Field(default=5, description="最大搜索深度（递归搜索时有效）")
    max_results: int = Field(default=100, description="最大结果数量")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """验证pattern不为空."""
        if not v or not v.strip():
            raise ValueError("pattern不能为空")
        return v.strip()

    @field_validator("max_depth")
    @classmethod
    def validate_max_depth(cls, v: int) -> int:
        """验证max_depth."""
        if v < 1:
            raise ValueError("max_depth必须 >= 1")
        if v > 10:
            raise ValueError("max_depth最大为 10")
        return v

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, v: int) -> int:
        """验证max_results."""
        if v < 1:
            raise ValueError("max_results必须 >= 1")
        if v > 500:
            raise ValueError("max_results最大为 500")
        return v


class GrepParams(ToolParameters):
    """内容搜索参数."""

    pattern: str = Field(..., description="正则表达式搜索模式")
    path: str = Field(default=".", description="搜索路径（文件或目录）")
    glob: str | None = Field(default=None, description="文件类型过滤，如 '*.py'")
    output_mode: str = Field(default="content", description="输出模式: content/files/count")
    context: int = Field(default=2, description="匹配前后显示的行数")
    max_results: int = Field(default=50, description="最大结果数")
    max_depth: int = Field(default=5, description="最大搜索深度")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """验证pattern不为空."""
        if not v or not v.strip():
            raise ValueError("pattern不能为空")
        return v.strip()

    @field_validator("output_mode")
    @classmethod
    def validate_output_mode(cls, v: str) -> str:
        """验证输出模式."""
        valid_modes = ["content", "files", "count"]
        if v not in valid_modes:
            raise ValueError(f"output_mode必须是其中之一: {valid_modes}")
        return v

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, v: int) -> int:
        """验证最大结果数."""
        if v < 1:
            raise ValueError("max_results必须 >= 1")
        if v > 500:
            raise ValueError("max_results最大为 500")
        return v


class GlobTool(BaseTool):
    """文件匹配搜索工具."""

    name: str = "glob"
    description: str = """使用glob模式搜索文件。
使用场景：查找特定类型的文件、搜索项目中的文件等。
支持的pattern语法：
- '*' 匹配任意字符（不含/）
- '**' 匹配任意层级目录
- '?' 匹配单个字符
- '[abc]' 匹配括号内任一字符
示例：
- '*.py' 所有Python文件
- '**/*.js' 所有子目录中的JS文件
- 'src/**/test_*.py' src目录下所有test_开头的py文件
参数：
- max_depth: 最大搜索深度（默认5，最大10）
- max_results: 最大结果数（默认100，最大500）"""

    IGNORE_DIRS: ClassVar[set[str]] = {
        ".git", "__pycache__", ".pytest_cache", "node_modules",
        ".venv", "venv", ".env", "dist", "build", ".tox",
        ".idea", ".vscode", ".vs", "target", ".claude"
    }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        max_depth: int = 5,
        max_results: int = 100,
        **kwargs: Any
    ) -> ToolResult:
        """执行glob搜索."""
        try:
            base_path = Path(path).expanduser().resolve()

            if not base_path.exists():
                return ToolResult.failure(f"路径不存在: {path}")

            if not base_path.is_dir():
                return ToolResult.failure(f"路径不是目录: {path}")

            # 执行搜索
            matches = list(self._glob_search(base_path, pattern, max_depth, max_results))
            matches.sort()

            # 检查结果是否被截断
            truncated = len(matches) >= max_results

            if not matches:
                return ToolResult.ok(
                    f"未找到匹配 '{pattern}' 的文件",
                    pattern=pattern,
                    path=str(base_path),
                    matches=[],
                    count=0,
                )

            # 格式化结果
            result_lines = [f"找到 {len(matches)} 个匹配文件:"]
            if truncated:
                result_lines.append(f"(结果已截断，仅显示前 {max_results} 个)")
            result_lines.extend(str(m.relative_to(base_path)) for m in matches)

            return ToolResult.ok(
                "\n".join(result_lines),
                pattern=pattern,
                path=str(base_path),
                matches=[str(m) for m in matches],
                count=len(matches),
                truncated=truncated,
                max_depth=max_depth,
            )

        except Exception as e:
            return ToolResult.failure(f"搜索失败: {e}", pattern=pattern)

    def _glob_search(
        self,
        base_path: Path,
        pattern: str,
        max_depth: int,
        max_results: int
    ) -> Any:
        """递归搜索匹配的文件 - 使用优化的遍历策略."""
        result_count = 0
        
        if pattern.startswith("**/"):
            # 递归搜索 - 使用 os.walk 更高效
            remaining = pattern[3:]  # 去掉 '**/'
            current_depth = 0
            
            for root, dirs, files in os.walk(base_path):
                # 检查深度限制
                if current_depth >= max_depth:
                    # 不再深入子目录
                    dirs.clear()
                    continue
                
                # 过滤掉忽略的目录
                dirs[:] = [
                    d for d in dirs
                    if d not in self.IGNORE_DIRS and not d.startswith(".")
                ]
                
                # 检查当前目录下的文件
                for filename in files:
                    if result_count >= max_results:
                        return
                    
                    if filename.startswith("."):
                        continue
                    
                    # 使用 fnmatch 匹配模式
                    if fnmatch.fnmatch(filename, remaining):
                        file_path = Path(root) / filename
                        if file_path.exists():
                            yield file_path
                            result_count += 1
                
                current_depth += 1
        else:
            # 单层搜索 - 使用 glob
            for path in base_path.glob(pattern):
                if result_count >= max_results:
                    return
                if self._should_include(path):
                    yield path
                    result_count += 1

    def _should_include(self, path: Path) -> bool:
        """检查路径是否应该包含在结果中."""
        if not path.exists():
            return False

        # 跳过隐藏文件和目录
        for part in path.parts:
            if part.startswith(".") and part not in (".", ".."):
                if part in self.IGNORE_DIRS:
                    return False

        return True

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return GlobParams.model_json_schema()


class GrepTool(BaseTool):
    """内容搜索工具."""

    name: str = "grep"
    description: str = """在文件中搜索匹配正则表达式的内容。
使用场景：搜索代码中的特定模式、查找函数定义、搜索变量名等。
支持的功能：
- 正则表达式搜索
- 文件类型过滤（glob模式）
- 显示匹配行及其上下文
- 限制结果数量避免token溢出
- 控制搜索深度避免性能问题
注意：
- 默认显示匹配行及其前后2行
- 二进制文件会被跳过
- 默认最大返回50条结果
- 默认最大搜索深度5层"""

    IGNORE_DIRS: ClassVar[set[str]] = {
        ".git", "__pycache__", ".pytest_cache", "node_modules",
        ".venv", "venv", ".env", "dist", "build", ".tox",
        ".idea", ".vscode", ".vs", "target", ".claude"
    }

    # 二进制文件扩展名
    BINARY_EXTENSIONS: ClassVar[set[str]] = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
        ".mp3", ".mp4", ".avi", ".mov", ".wmv",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".pyc", ".pyo", ".class", ".o", ".a",
    }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        output_mode: str = "content",
        context: int = 2,
        max_results: int = 50,
        max_depth: int = 5,
        **kwargs: Any
    ) -> ToolResult:
        """执行grep搜索."""
        try:
            base_path = Path(path).expanduser().resolve()

            if not base_path.exists():
                return ToolResult.failure(f"路径不存在: {path}")

            # 编译正则表达式
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return ToolResult.failure(f"无效的正则表达式: {e}")

            results = []

            if base_path.is_file():
                # 搜索单个文件
                result = self._search_file(
                    base_path, regex, context, max_results - len(results)
                )
                if result:
                    results.append((base_path, result))
            else:
                # 搜索目录
                results = self._search_directory(
                    base_path, regex, glob, context, max_results, max_depth
                )

            if not results:
                return ToolResult.ok(
                    f"未找到匹配 '{pattern}' 的内容",
                    pattern=pattern,
                    path=str(base_path),
                    matches=[],
                    count=0,
                )

            # 根据输出模式格式化结果
            if output_mode == "files":
                file_list = [str(f[0]) for f in results]
                content = "匹配的文件:\n" + "\n".join(file_list)
            elif output_mode == "count":
                total = sum(len(matches) for _, matches in results)
                content = f"总共找到 {total} 处匹配"
            else:  # content
                content = self._format_content_results(results, context)

            total_matches = sum(len(matches) for _, matches in results)

            return ToolResult.ok(
                content,
                pattern=pattern,
                path=str(base_path),
                files_matched=len(results),
                match_count=total_matches,
                truncated=total_matches >= max_results,
            )

        except Exception as e:
            return ToolResult.failure(f"搜索失败: {e}", pattern=pattern)

    def _search_directory(
        self,
        base_path: Path,
        regex: re.Pattern,
        glob_pattern: str | None,
        context: int,
        max_results: int,
        max_depth: int = 5
    ) -> list[tuple[Path, list[dict]]]:
        """搜索目录中的所有文件."""
        results = []

        for file_path in self._iter_files(base_path, glob_pattern, max_depth):
            if len(results) >= max_results:
                break

            file_results = self._search_file(
                file_path, regex, context, max_results - sum(len(r[1]) for r in results)
            )
            if file_results:
                results.append((file_path, file_results))

        return results

    def _iter_files(
        self,
        base_path: Path,
        glob_pattern: str | None,
        max_depth: int = 5
    ) -> Any:
        """遍历目录中的文件 - 使用优化的 os.walk."""
        current_depth = 0
        
        for root, dirs, files in os.walk(base_path):
            # 检查深度限制
            if current_depth >= max_depth:
                dirs.clear()
                continue
            
            # 过滤掉忽略的目录和隐藏目录
            dirs[:] = [
                d for d in dirs
                if d not in self.IGNORE_DIRS and not d.startswith(".")
            ]
            
            # 处理文件
            for filename in files:
                # 跳过隐藏文件
                if filename.startswith("."):
                    continue
                
                file_path = Path(root) / filename
                
                # 跳过二进制文件
                if file_path.suffix.lower() in self.BINARY_EXTENSIONS:
                    continue
                
                # 应用glob过滤
                if glob_pattern and not fnmatch.fnmatch(filename, glob_pattern):
                    continue
                
                yield file_path
            
            current_depth += 1

    def _search_file(
        self,
        file_path: Path,
        regex: re.Pattern,
        context: int,
        max_matches: int
    ) -> list[dict]:
        """搜索单个文件."""
        results = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (IOError, OSError):
            return results

        for i, line in enumerate(lines, start=1):
            if len(results) >= max_matches:
                break

            if regex.search(line):
                # 获取上下文
                start = max(0, i - context - 1)
                end = min(len(lines), i + context)

                context_lines = []
                for j in range(start, end):
                    prefix = ">>> " if j == i - 1 else "    "
                    context_lines.append(f"{prefix}{j + 1:4d} | {lines[j].rstrip()}")

                results.append({
                    "line": i,
                    "content": line.rstrip(),
                    "context": "\n".join(context_lines),
                })

        return results

    def _format_content_results(
        self,
        results: list[tuple[Path, list[dict]]],
        context: int
    ) -> str:
        """格式化内容搜索结果."""
        lines = []

        for file_path, matches in results:
            lines.append(f"\n{'=' * 60}")
            lines.append(f"文件: {file_path}")
            lines.append(f"{'=' * 60}")

            for match in matches:
                lines.append(match["context"])
                lines.append("")

        return "\n".join(lines)

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return GrepParams.model_json_schema()


# 注册工具
tool_registry.register(GlobTool())
tool_registry.register(GrepTool())
