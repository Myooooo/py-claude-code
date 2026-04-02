"""Rich美化界面模块."""

import sys
from typing import Any, Iterator

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .config import Config


# 全局console实例
console = Console()


class UI:
    """UI管理类."""

    def __init__(self, config: Config | None = None):
        """初始化UI."""
        self.config = config or Config()
        self.console = Console(
            width=self.config.code_width,
            soft_wrap=True,
        )

    def print_welcome(self) -> None:
        """打印欢迎信息."""
        title = Text("🤖 Py Claude Code", style="bold cyan")
        subtitle = Text("Python版 Claude Code 编程助手", style="dim")

        panel = Panel(
            Align.center(f"{title}\n{subtitle}"),
            box=box.ROUNDED,
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(panel)

        # 帮助提示
        self.console.print("[bold]命令:[/bold]")
        self.console.print("  [cyan]/help[/cyan]     显示帮助")
        self.console.print("  [cyan]/clear[/cyan]    清空对话历史")
        self.console.print("  [cyan]/reset[/cyan]    重置会话")
        self.console.print("  [cyan]/exit[/cyan]     退出程序")
        self.console.print("  [cyan]/tools[/cyan]    查看可用工具")
        self.console.print("  [cyan]/cost[/cyan]     查看成本统计")
        self.console.print("  [cyan]/budget[/cyan]   查看预算")
        self.console.print()
        self.console.print("[bold]提示:[/bold]")
        self.console.print("  • 直接输入问题开始对话")
        self.console.print("  • 支持多轮对话和工具调用")
        self.console.print("  • 使用 [cyan]Ctrl+C[/cyan] 取消当前操作")
        self.console.print("  • 成本追踪已启用，每次请求后显示费用")
        self.console.print()

    def print_goodbye(self) -> None:
        """打印退出信息."""
        self.console.print("\n[dim]👋 再见！[/dim]")

    def print_error(self, message: str) -> None:
        """打印错误信息."""
        self.console.print(f"[bold red]错误:[/bold red] {message}")

    def print_warning(self, message: str) -> None:
        """打印警告信息."""
        self.console.print(f"[bold yellow]警告:[/bold yellow] {message}")

    def print_info(self, message: str) -> None:
        """打印信息."""
        self.console.print(f"[dim]{message}[/dim]")

    def print_success(self, message: str) -> None:
        """打印成功信息."""
        self.console.print(f"[bold green]✓[/bold green] {message}")

    def print_user_message(self, content: str) -> None:
        """打印用户消息."""
        panel = Panel(
            Markdown(content),
            title="[bold blue]You[/bold blue]",
            title_align="left",
            border_style="blue",
            box=box.ROUNDED,
        )
        self.console.print(panel)

    def print_assistant_message(self, content: str) -> None:
        """打印助手消息."""
        panel = Panel(
            Markdown(content),
            title="[bold green]Assistant[/bold green]",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
        )
        self.console.print(panel)

    def print_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """打印工具调用."""
        args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
        text = Text(f"🔧 {tool_name}({args_str})", style="dim yellow")
        self.console.print(text)

    def print_tool_result(self, tool_name: str, success: bool) -> None:
        """打印工具执行结果."""
        if success:
            self.console.print(f"  [dim green]✓ {tool_name} 完成[/dim green]")
        else:
            self.console.print(f"  [dim red]✗ {tool_name} 失败[/dim red]")

    def print_cost_info(self, last_cost: float, session_cost: float) -> None:
        """打印成本信息."""
        if last_cost < 0.0001:
            cost_text = f"本次: < $0.0001 | 会话: ${session_cost:.4f}"
        else:
            cost_text = f"本次: ${last_cost:.4f} | 会话: ${session_cost:.4f}"
        self.console.print(f"  [dim blue]💰 {cost_text}[/dim blue]")

    def print_budget_warning(self, message: str, critical: bool = False) -> None:
        """打印预算警告."""
        if critical:
            self.console.print(f"  [bold red]🚨 {message}[/bold red]")
        else:
            self.console.print(f"  [bold yellow]⚠️ {message}[/bold yellow]")

    def print_code(
        self,
        code: str,
        language: str = "python",
        filename: str | None = None,
    ) -> None:
        """打印代码块."""
        syntax = Syntax(
            code,
            language,
            theme=self.config.theme,
            line_numbers=True,
            word_wrap=True,
        )

        title = filename or language
        panel = Panel(
            syntax,
            title=f"[bold]{title}[/bold]",
            border_style="cyan",
            box=box.ROUNDED,
        )
        self.console.print(panel)

    def print_file_tree(
        self,
        tree_data: dict[str, Any],
        title: str = "目录结构",
    ) -> None:
        """打印文件树."""
        tree = Tree(f"[bold cyan]📁 {tree_data.get('name', 'root')}[/bold cyan]")
        self._build_tree(tree, tree_data.get("children", []))

        panel = Panel(
            tree,
            title=f"[bold]{title}[/bold]",
            border_style="cyan",
            box=box.ROUNDED,
        )
        self.console.print(panel)

    def _build_tree(self, tree: Tree, children: list[dict]) -> None:
        """递归构建树."""
        for child in children:
            name = child.get("name", "")
            if child.get("type") == "directory":
                branch = tree.add(f"[cyan]📁 {name}[/cyan]")
                self._build_tree(branch, child.get("children", []))
            else:
                icon = self._get_file_icon(name)
                tree.add(f"{icon} {name}")

    def _get_file_icon(self, filename: str) -> str:
        """根据文件类型返回图标."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        icons = {
            "py": "🐍",
            "js": "📜",
            "ts": "📘",
            "jsx": "⚛️",
            "tsx": "⚛️",
            "json": "📋",
            "md": "📝",
            "txt": "📄",
            "yml": "⚙️",
            "yaml": "⚙️",
            "html": "🌐",
            "css": "🎨",
            "sql": "🗄️",
            "sh": "⚡",
            "dockerfile": "🐳",
        }

        return icons.get(ext, "📄")

    def print_table(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        title: str | None = None,
    ) -> None:
        """打印表格."""
        table = Table(
            title=title,
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        for col in columns:
            table.add_column(col)

        for row in data:
            table.add_row(*[str(row.get(col, "")) for col in columns])

        self.console.print(table)

    def print_tools_list(self, tools: list[dict[str, str]]) -> None:
        """打印工具列表."""
        table = Table(
            title="[bold]可用工具[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("名称", style="cyan")
        table.add_column("描述", style="green")

        for tool in tools:
            table.add_row(
                tool.get("name", ""),
                tool.get("description", "")[:100] + "..."
                if len(tool.get("description", "")) > 100
                else tool.get("description", ""),
            )

        self.console.print(table)

    def create_progress(self, description: str = "处理中...") -> Progress:
        """创建进度条."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        )

    def print_stream_start(self) -> None:
        """开始流式输出."""
        self.console.print("[bold green]Assistant:[/bold green] ", end="")

    def print_stream_chunk(self, chunk: str) -> None:
        """打印流式输出块."""
        self.console.print(chunk, end="")

    def print_stream_end(self) -> None:
        """结束流式输出."""
        self.console.print()

    def get_input(self, prompt: str = "") -> str:
        """获取用户输入."""
        if prompt:
            self.console.print(f"[bold blue]{prompt}[/bold blue]", end="")
        try:
            return input()
        except EOFError:
            return ""

    def print_help(self) -> None:
        """打印帮助信息."""
        help_text = """
# Py Claude Code 帮助

## 基本用法
直接输入问题或指令，助手将使用AI模型回答。

## 特殊命令
- `/help` - 显示此帮助信息
- `/clear` - 清空当前对话历史
- `/reset` - 重置当前会话（清除所有上下文）
- `/exit` 或 `/quit` - 退出程序
- `/tools` - 查看所有可用工具
- `/model` - 查看当前使用的模型
- `/tokens` - 查看Token和成本使用统计
- `/cost` - 查看当前会话成本详情
- `/cost-daily` - 查看今日成本汇总
- `/cost-weekly` - 查看本周成本汇总
- `/cost-monthly` - 查看本月成本汇总
- `/budget` - 查看预算配置和使用情况
- `/cost-report` - 导出成本报告
- `/sessions` - 列出所有会话
- `/checkpoint` - 创建检查点
- `/undo` - 回滚到上一检查点
- `/redo` - 恢复检查点
- `/save` - 手动保存会话
- `/load` - 加载会话
- `/history` - 查看对话历史

## 可用工具
助手可以自动调用以下工具：

### 文件操作
- `file_read` - 读取文件内容
- `file_write` - 创建或覆盖文件
- `file_edit` - 编辑已有文件
- `view` - 查看目录结构

### 命令执行
- `bash` - 执行Bash命令

### 搜索
- `glob` - 文件匹配搜索
- `grep` - 内容搜索

## 快捷键
- `Ctrl+C` - 取消当前操作
- `Ctrl+D` - 退出程序

## 环境变量
- `OPENAI_API_KEY` - OpenAI API密钥（必需）
- `OPENAI_BASE_URL` - API基础URL（可选）
- `OPENAI_MODEL` - 使用的模型（默认: gpt-4o）
        """
        self.console.print(Markdown(help_text))

    def status(self, message: str) -> "StatusContext":
        """返回状态上下文管理器."""
        return StatusContext(self.console, message)


class StatusContext:
    """状态显示上下文管理器."""

    def __init__(self, console: Console, message: str):
        """初始化."""
        self.console = console
        self.message = message
        self.live: Live | None = None

    def __enter__(self) -> "StatusContext":
        """进入上下文."""
        self.live = Live(
            self._render_spinner(),
            console=self.console,
            refresh_per_second=10,
        )
        self.live.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文."""
        if self.live:
            self.live.stop()
            if exc_type is None:
                self.console.print(f"[green]✓[/green] {self.message}")
            else:
                self.console.print(f"[red]✗[/red] {self.message}")

    def _render_spinner(self) -> Text:
        """渲染spinner."""
        return Text(f"⏳ {self.message}...", style="dim")

    def update(self, message: str) -> None:
        """更新状态消息."""
        self.message = message


class StreamingPanel:
    """流式输出面板."""

    def __init__(self, console: Console, title: str = "Assistant"):
        """初始化."""
        self.console = console
        self.title = title
        self.content = ""
        self.live: Live | None = None

    def __enter__(self) -> "StreamingPanel":
        """进入上下文."""
        self.live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=10,
            auto_refresh=True,
        )
        self.live.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文."""
        if self.live:
            self.live.stop()
            # 打印最终结果
            self.console.print(self._render())

    def _render(self) -> Panel:
        """渲染面板."""
        return Panel(
            Markdown(self.content) if self.content else Text("思考中...", style="dim"),
            title=f"[bold green]{self.title}[/bold green]",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
        )

    def append(self, text: str) -> None:
        """追加内容."""
        self.content += text


# 便捷函数
def get_console() -> Console:
    """获取全局console实例."""
    return console


def print_message(role: str, content: str) -> None:
    """打印消息."""
    ui = UI()
    if role == "user":
        ui.print_user_message(content)
    elif role == "assistant":
        ui.print_assistant_message(content)
    else:
        console.print(f"[{role}] {content}")
