"""Bash命令执行工具."""

import asyncio
import shlex
from typing import Any
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

    # 危险命令警告列表
    DANGEROUS_PATTERNS = [
        "rm -rf /",
        "> /dev/sda",
        "mkfs",
        "dd if=/dev/zero",
        ":(){ :|:& };:",  # fork bomb
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
            # 安全检查
            warning = self._check_dangerous_command(command)
            if warning:
                return ToolResult.error(
                    f"检测到潜在危险命令: {warning}\n请确认您的操作意图。",
                    command=command,
                )

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
            )

        except Exception as e:
            return ToolResult.error(f"执行命令失败: {e}", command=command)

    def _check_dangerous_command(self, command: str) -> str | None:
        """检查命令是否包含危险模式."""
        cmd_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in cmd_lower:
                return pattern
        return None

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数schema."""
        return BashParams.model_json_schema()


# 注册工具
tool_registry.register(BashTool())
