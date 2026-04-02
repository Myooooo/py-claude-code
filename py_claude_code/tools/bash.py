"""Bash命令执行工具."""

import asyncio
import re
import shlex
from typing import Any, ClassVar
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry


class BashParams(ToolParameters):
    """Bash命令执行参数."""

    command: str = Field(..., description="要执行的命令")
    timeout: int = Field(default=120, description="命令超时时间（秒）")
    cwd: str | None = Field(default=None, description="工作目录")

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """验证命令不为空."""
        if not v or not v.strip():
            raise ValueError("命令不能为空")
        return v.strip()

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """验证超时时间."""
        if v < 1:
            raise ValueError("超时时间必须 >= 1 秒")
        if v > 600:
            raise ValueError("超时时间最大为 600 秒")
        return v


class BashTool(BaseTool):
    """Bash命令执行工具."""

    name: str = "bash"
    description: str = """在shell中执行Bash命令。
使用场景：运行脚本、执行系统命令、管理文件、安装依赖等。
注意：
- 命令会在当前工作目录执行
- 默认超时时间为120秒
- 支持管道和重定向等shell特性
- 危险操作（rm -rf等）请谨慎使用
- 长时间运行的命令会被终止
- 环境变量会继承当前shell"""

    # 危险命令警告列表 - 使用正则表达式，更健壮
    DANGEROUS_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        # 文件系统破坏
        (r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+.*[/~]", "递归删除根目录或家目录"),
        (r"\brm\s+.*\s+-[a-zA-Z]*f[a-zA-Z]*\s+.*[/~]", "递归删除根目录或家目录"),
        (r">\s*/dev/sda", "直接写入磁盘设备"),
        (r"mkfs\.[a-z]+\s+/dev/[hs]d", "格式化磁盘分区"),
        (r"dd\s+if=/dev/zero\s+of=/dev/[hs]d", "清零磁盘"),
        (r"dd\s+if=/dev/urandom\s+of=/dev/[hs]d", "随机填充磁盘"),
        # Fork bomb
        (r":\(\)\s*\{\s*:\s*\|.*&\s*\};\s*:", "Fork bomb"),
        # 权限提升
        (r"chmod\s+-[a-zA-Z]*777[a-zA-Z]*\s+/-", "给根目录777权限"),
        (r"chmod\s+-[a-zA-Z]*000[a-zA-Z]*\s+/-", "移除根目录所有权限"),
        # 网络攻击
        (r"ping\s+-[a-zA-Z]*f[a-zA-Z]*.*\s+\d+\.\d+\.\d+\.\d+", "Ping flood攻击"),
    ]

    # 需要额外确认的危险操作
    CAUTION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*", "递归删除"),
        (r"\brm\s+.*\*", "使用通配符删除"),
        (r"\bgit\s+reset\s+--hard", "强制重置git仓库"),
        (r"\bgit\s+clean\s+-[a-zA-Z]*f[a-zA-Z]*", "强制清理git未跟踪文件"),
        (r"\bdropdb\s+", "删除数据库"),
        (r"\bdocker\s+system\s+prune", "清理Docker系统"),
    ]

    async def execute(
        self,
        command: str,
        timeout: int = 120,
        cwd: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        """执行Bash命令."""
        try:
            # 安全检查 - 危险命令
            danger_check = self._check_dangerous_command(command)
            if danger_check:
                pattern, description = danger_check
                return ToolResult.error(
                    f"🚫 检测到危险操作: {description}\n"
                    f"匹配模式: {pattern}\n"
                    f"此命令已被阻止执行。如需执行，请手动在终端运行。",
                    command=command,
                    blocked_pattern=pattern,
                    danger_type=description,
                )
            
            # 警告检查 - 需要谨慎的命令
            caution_warnings = self._check_caution_command(command)
            warning_msg = None
            if caution_warnings:
                warnings_text = "\n".join([f"  - {desc}" for _, desc in caution_warnings])
                warning_msg = f"⚠️ 警告：此命令包含需要谨慎的操作:\n{warnings_text}"

            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                # 等待命令执行完成
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.error(
                    f"命令执行超时（{timeout}秒）",
                    command=command,
                    return_code=-1,
                )

            # 解码输出
            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

            # 构建结果
            result_lines = []
            if warning_msg:
                result_lines.append(warning_msg)
                result_lines.append("")
            if stdout_text:
                result_lines.append("=== 标准输出 ===")
                result_lines.append(stdout_text.rstrip())
            if stderr_text:
                result_lines.append("=== 标准错误 ===")
                result_lines.append(stderr_text.rstrip())

            content = "\n".join(result_lines) if result_lines else "（无输出）"

            return ToolResult.ok(
                content,
                command=command,
                return_code=process.returncode,
                stdout_length=len(stdout_text),
                stderr_length=len(stderr_text),
                success=process.returncode == 0,
                had_warnings=len(caution_warnings) > 0,
            )

        except Exception as e:
            return ToolResult.error(f"执行命令失败: {e}", command=command)

    def _check_dangerous_command(self, command: str) -> tuple[str, str] | None:
        """检查命令是否包含危险模式.
        
        Returns:
            (pattern, description) 如果发现危险模式
            None 如果安全
        """
        # 标准化命令：处理多余空格
        normalized = ' '.join(command.split())
        
        # 检查危险模式
        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return (pattern, description)
        
        return None
    
    def _check_caution_command(self, command: str) -> list[tuple[str, str]]:
        """检查需要谨慎执行的命令.
        
        Returns:
            匹配的 (pattern, description) 列表
        """
        warnings = []
        normalized = ' '.join(command.split())
        
        for pattern, description in self.CAUTION_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                warnings.append((pattern, description))
        
        return warnings

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return BashParams.model_json_schema()


# 注册工具
tool_registry.register(BashTool())
