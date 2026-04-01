#!/bin/bash
# 启动开发环境脚本

WORKSPACE="/Users/fmy/.openclaw/workspace/code/py-claude-code"
cd "$WORKSPACE"

# 启动监控进程
echo "[$(date)] 启动监控进程..."
nohup python3 monitor.py > logs/monitor.log 2>&1 &
echo $! > logs/monitor.pid

# 启动Claude Code开发
echo "[$(date)] 启动Claude Code开发会话..."
tmux send-keys -t py-claude-dev "claude --permission-mode bypassPermissions --print '你需要实现一个Python版本的Claude Code编程助手，名为py-claude-code。

## 项目需求

### 1. 项目结构
在 /Users/fmy/.openclaw/workspace/code/py-claude-code/py_claude_code/ 目录下创建：
- __init__.py
- __main__.py
- cli.py - 使用typer的命令行入口
- chat.py - 对话管理
- llm.py - OpenAI API客户端
- ui.py - Rich美化界面
- config.py - 配置管理
- tools/ 目录:
  - __init__.py
  - base.py - 工具基类
  - file.py - 文件操作工具(file_read, file_write, file_edit)
  - bash.py - bash命令执行
  - search.py - 搜索工具(glob, grep, view)

### 2. 核心功能
- 多轮对话支持
- 工具调用系统（OpenAI function calling格式）
- 支持的工具：file_read, file_write, file_edit, bash, glob, grep, view
- 流式输出
- 使用pydantic进行数据验证
- 完整类型注解

### 3. 要求
- 兼容OpenAI Chat Completions API
- 从环境变量读取OPENAI_API_KEY和OPENAI_BASE_URL
- 代码质量高，有完整文档字符串
- 包含错误处理

请开始实现，创建目录结构和所有文件。完成后提交到git。'" Enter

echo "[$(date)] 开发环境启动完成！"
echo "- 监控进程PID: $(cat logs/monitor.pid)"
echo "- Claude Code在tmux会话: py-claude-dev"
echo "- Gemini Review在tmux会话: gemini-review"
