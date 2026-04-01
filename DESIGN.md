# py-claude-code 设计文档

## 概述
实现一个类似Claude Code的AI编程助手，使用Python编写，兼容OpenAI Chat Completions API格式。

## 核心模块

### 1. CLI入口 (cli.py)
- 命令行参数解析
- 配置加载
- 主循环启动

### 2. 对话管理 (chat.py)
- 多轮对话维护
- 上下文窗口管理
- 历史记录存储

### 3. 工具系统 (tools/)
- file_read: 读取文件内容
- file_write: 写入/修改文件
- file_edit: 编辑文件特定位置
- bash: 执行bash命令
- glob: 文件搜索
- grep: 文本搜索
- view: 查看目录结构

### 4. LLM接口 (llm.py)
- OpenAI API客户端
- 工具调用处理
- 流式输出支持

### 5. UI界面 (ui.py)
- Rich库美化输出
- 代码高亮
- 进度显示

## 项目结构
```
py_claude_code/
├── __init__.py
├── __main__.py
├── cli.py          # 命令行入口
├── chat.py         # 对话管理
├── llm.py          # LLM接口
├── ui.py           # UI组件
├── tools/          # 工具实现
│   ├── __init__.py
│   ├── base.py     # 工具基类
│   ├── file.py     # 文件操作
│   ├── bash.py     # 命令执行
│   └── search.py   # 搜索工具
└── config.py       # 配置管理
```

## API兼容性
- 支持OpenAI Chat Completions API
- 支持function calling/tools
- 支持流式响应
