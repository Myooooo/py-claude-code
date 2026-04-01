# Py Claude Code

Python版 Claude Code 编程助手，兼容 OpenAI Chat Completions API。

## 功能特性

- **多轮对话**: 支持上下文感知的连续对话
- **工具系统**: 内置文件操作、命令执行、搜索等工具
- **流式输出**: 实时显示AI响应
- **工具调用**: 自动调用函数完成复杂任务
- **Rich美化界面**: 美观的命令行界面
- **完整类型注解**: 支持类型检查和代码补全

## 安装

### 从源码安装

```bash
git clone <repository-url>
cd py-claude-code
pip install -r requirements.txt
```

### 依赖包

- openai >= 1.30.0
- pydantic >= 2.0.0
- rich >= 13.0.0
- typer >= 0.12.0

## 配置

### 环境变量

创建 `.env` 文件或在环境中设置：

```bash
# 必需
OPENAI_API_KEY=your-api-key

# 可选
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

### 配置选项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| OPENAI_API_KEY | - | OpenAI API密钥（必需） |
| OPENAI_BASE_URL | https://api.openai.com/v1 | API基础URL |
| OPENAI_MODEL | gpt-4o | 使用的模型 |

## 使用方法

### 交互式模式

```bash
# 启动交互式对话
python -m py_claude_code

# 或使用CLI入口
python py_claude_code/cli.py
```

### 单次查询模式

```bash
# 单次查询
python -m py_claude_code "请解释Python中的装饰器"

# 指定模型
python -m py_claude_code "优化这段代码" --model gpt-4o-mini
```

### 特殊命令

在交互式模式下，可以使用以下命令：

- `/help` - 显示帮助信息
- `/clear` - 清空对话历史
- `/reset` - 重置当前会话
- `/exit` 或 `/quit` - 退出程序
- `/tools` - 查看可用工具
- `/model` - 查看当前使用的模型

## 可用工具

### 文件操作

- **file_read** - 读取文件内容
  ```
  参数: file_path, offset, limit
  ```

- **file_write** - 创建或覆盖文件
  ```
  参数: file_path, content
  ```

- **file_edit** - 编辑已有文件
  ```
  参数: file_path, old_string, new_string
  ```

- **view** - 查看目录结构
  ```
  参数: path, depth
  ```

### 命令执行

- **bash** - 执行Bash命令
  ```
  参数: command, timeout, cwd
  ```

### 搜索

- **glob** - 文件匹配搜索
  ```
  参数: pattern, path
  ```

- **grep** - 内容搜索
  ```
  参数: pattern, path, glob, output_mode, context, max_results
  ```

## 代码示例

### 基础对话

```python
import asyncio
from py_claude_code import ChatSession, load_config

async def main():
    config = load_config()
    session = ChatSession(config)

    response = await session.send_message("你好！")
    print(response)

asyncio.run(main())
```

### 使用工具调用

```python
import asyncio
from py_claude_code import ChatSession, load_config

async def main():
    config = load_config()
    session = ChatSession(config)

    # AI会自动调用工具来完成任务
    response = await session.send_message(
        "请查看当前目录结构",
        use_tools=True
    )
    print(response)

asyncio.run(main())
```

### 直接调用工具

```python
import asyncio
from py_claude_code.tools import FileReadTool, BashTool

async def main():
    # 读取文件
    tool = FileReadTool()
    result = await tool.execute(file_path="example.py")
    print(result.content)

    # 执行命令
    bash_tool = BashTool()
    result = await bash_tool.execute(command="ls -la")
    print(result.content)

asyncio.run(main())
```

### 流式输出

```python
import asyncio
from py_claude_code import ChatSession, load_config

async def main():
    config = load_config()
    session = ChatSession(config)

    stream = await session.send_message(
        "写一个Python快速排序",
        stream=True
    )

    async for chunk in stream:
        print(chunk, end="", flush=True)
    print()

asyncio.run(main())
```

## 项目结构

```
py_claude_code/
├── __init__.py          # 包入口
├── __main__.py          # python -m 支持
├── cli.py               # 命令行接口
├── config.py            # 配置管理
├── chat.py              # 对话管理
├── llm.py               # OpenAI API客户端
├── ui.py                # Rich界面
└── tools/               # 工具目录
    ├── __init__.py
    ├── base.py          # 工具基类
    ├── file.py          # 文件操作工具
    ├── bash.py          # Bash命令工具
    └── search.py        # 搜索工具
```

## 快捷键

- `Ctrl+C` - 取消当前操作
- `Ctrl+D` - 退出程序（发送EOF）

## 安全说明

- Bash工具会检查危险命令（如 `rm -rf /`）
- 文件操作会自动跳过系统目录（如 `.git`, `node_modules`）
- 命令执行默认超时120秒

## 许可证

MIT License
