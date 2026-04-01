"""命令行入口."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.text import Text

from .config import Config, load_config
from .chat import ChatManager, ChatSession
from .tools.base import tool_registry
from .ui import UI, console

# 创建Typer应用
app = typer.Typer(
    name="py-claude-code",
    help="Python版 Claude Code 编程助手",
    add_completion=False,
)


@app.command()
def main(
    prompt: Optional[str] = typer.Argument(
        None,
        help="单次查询提示词（非交互模式）",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="使用的模型名称",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        help="OpenAI API Key",
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url", "-b",
        help="OpenAI API Base URL",
    ),
    system_prompt: Optional[str] = typer.Option(
        None,
        "--system", "-s",
        help="系统提示词",
    ),
    no_tools: bool = typer.Option(
        False,
        "--no-tools",
        help="禁用工具调用",
    ),
    version: bool = typer.Option(
        False,
        "--version", "-v",
        help="显示版本信息",
        is_flag=True,
    ),
) -> None:
    """Py Claude Code - Python版 Claude Code 编程助手."""

    if version:
        rprint("[cyan]Py Claude Code[/cyan] [bold]v0.1.0[/bold]")
        raise typer.Exit()

    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        rprint(f"[bold red]配置错误:[/bold red] {e}")
        rprint("请设置 OPENAI_API_KEY 环境变量或创建 .env 文件")
        raise typer.Exit(1)

    # 应用命令行参数覆盖
    if model:
        config.model = model
    if api_key:
        config.api_key = api_key
    if base_url:
        config.base_url = base_url
    if system_prompt:
        config.system_prompt = system_prompt

    # 运行
    if prompt:
        # 单次查询模式
        asyncio.run(run_single(prompt, config, not no_tools))
    else:
        # 交互式模式
        asyncio.run(run_interactive(config, not no_tools))


async def run_single(
    prompt: str,
    config: Config,
    use_tools: bool,
) -> None:
    """单次查询模式."""
    ui = UI(config)

    try:
        session = ChatSession(config)

        with ui.status("思考中..."):
            response = await session.send_message(prompt, use_tools=use_tools)

        if isinstance(response, str):
            ui.print_assistant_message(response)
        else:
            async for chunk in response:
                ui.print_stream_chunk(chunk)
            ui.print_stream_end()

    except Exception as e:
        ui.print_error(str(e))
        raise typer.Exit(1)


async def run_interactive(
    config: Config,
    use_tools: bool,
) -> None:
    """交互式模式."""
    ui = UI(config)
    ui.print_welcome()

    # 创建会话
    session = ChatSession(config)

    while True:
        try:
            # 获取用户输入
            user_input = input("\n[You] ").strip()

            if not user_input:
                continue

            # 处理特殊命令
            if user_input.startswith("/"):
                should_exit = await handle_command(
                    user_input, session, ui, use_tools
                )
                if should_exit:
                    break
                continue

            # 处理普通对话
            await handle_chat(user_input, session, ui, use_tools)

        except KeyboardInterrupt:
            rprint("\n[dim]操作已取消[/dim]")
            continue
        except EOFError:
            break

    ui.print_goodbye()


async def handle_command(
    command: str,
    session: ChatSession,
    ui: UI,
    use_tools: bool,
) -> bool:
    """处理特殊命令.

    Returns:
        True if should exit
    """
    cmd = command.lower().strip()

    if cmd in ["/exit", "/quit", "/q"]:
        return True

    elif cmd == "/help":
        ui.print_help()

    elif cmd == "/clear":
        session.clear_history()
        ui.print_success("对话历史已清空")

    elif cmd == "/reset":
        session.clear_history()
        ui.print_success("会话已重置")

    elif cmd == "/tools":
        tools = [
            {"name": tool.name, "description": tool.description}
            for tool in tool_registry.list_tools()
        ]
        ui.print_tools_list(tools)

    elif cmd == "/model":
        rprint(f"[cyan]当前模型:[/cyan] [bold]{session.config.model}[/bold]")
        rprint(f"[cyan]Base URL:[/cyan] {session.config.base_url}")

    elif cmd == "/history":
        history = session.get_history()
        if not history:
            ui.print_info("暂无对话历史")
        else:
            for msg in history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if content:
                    preview = content[:100] + "..." if len(content) > 100 else content
                    rprint(f"[dim]{role}:[/dim] {preview}")

    elif cmd == "/checkpoint":
        name = session.create_checkpoint()
        ui.print_success(f"已创建检查点: {name}")

    elif cmd == "/undo":
        if session.undo():
            ui.print_success("已回滚到上一检查点")
        else:
            ui.print_warning("没有可回滚的检查点")

    elif cmd == "/redo":
        if session.redo():
            ui.print_success("已恢复检查点")
        else:
            ui.print_warning("没有可恢复的检查点")

    elif cmd == "/save":
        session.save()
        ui.print_success("会话已保存")

    elif cmd == "/load":
        if session.load():
            ui.print_success("会话已加载")
        else:
            ui.print_warning("没有找到保存的会话")

    elif cmd == "/tokens":
        metrics = session.get_token_metrics()
        if metrics:
            rprint(f"[cyan]Token使用统计:[/cyan]")
            rprint(f"  总Token数: {metrics.total_tokens}")
            rprint(f"  消息数量: {metrics.message_count}")
        else:
            ui.print_info("暂无Token统计")

    elif cmd == "/sessions":
        sessions = chat_manager.list_sessions()
        if sessions:
            rprint(f"[cyan]所有会话:[/cyan]")
            for sid in sessions[:10]:  # 只显示前10个
                current = " [当前]" if sid == chat_manager.current_session_id else ""
                rprint(f"  - {sid}{current}")
        else:
            ui.print_info("暂无会话")

    else:
        ui.print_warning(f"未知命令: {command}")
        rprint("[dim]输入 /help 查看可用命令[/dim]")

    return False


async def handle_chat(
    user_input: str,
    session: ChatSession,
    ui: UI,
    use_tools: bool,
) -> None:
    """处理普通对话."""
    # 显示用户消息
    ui.print_user_message(user_input)

    # 显示思考中状态
    with ui.status("思考中..."):
        try:
            response = await session.send_message(
                user_input,
                use_tools=use_tools,
                stream=False,
            )
        except Exception as e:
            ui.print_error(f"请求失败: {e}")
            return

    # 显示响应
    if isinstance(response, str):
        # 显示工具调用历史
        tool_history = session.get_tool_history()
        if tool_history:
            for tool_info in tool_history:
                tool_name = tool_info.get("tool", "unknown")
                success = tool_info.get("success", False)
                ui.print_tool_result(tool_name, success)
            # 清空本次的工具历史
            session.tool_history.clear()

        ui.print_assistant_message(response)


def run() -> None:
    """入口函数."""
    app()


if __name__ == "__main__":
    run()
