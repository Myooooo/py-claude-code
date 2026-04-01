# 上下文和记忆系统优化任务

## 当前问题
当前chat.py使用简单的消息数截断(max_messages=50)，与Claude Code原生实现差距较大。

## 需要实现的优化（按Claude Code架构）

### 1. Token-based Context Management
**文件**: chat.py, llm.py, config.py
**实现**:
- 添加tiktoken依赖，使用cl100k_base编码
- 每条消息计算token数
- ContextManager按max_context_tokens(默认100k)管理
- 超限后智能压缩：保留系统消息 + 最近对话 + 关键决策点

### 2. Tool Result Summarization
**文件**: chat.py, llm.py
**实现**:
- 工具结果>1000token时自动摘要
- 保留前200字符 + [摘要标记] + 后200字符
- 添加完整内容存储到tool_history供参考

### 3. Persistent Session Storage
**文件**: chat.py, 新建 storage.py
**实现**:
- SQLite存储会话历史
- ChatSession自动保存到数据库
- 启动时自动恢复会话
- 支持导出/导入会话

### 4. Checkpoint System
**文件**: chat.py, cli.py
**实现**:
- /checkpoint 命令保存检查点
- /undo 回滚到上一检查点
- /redo 恢复检查点
- 自动检查点（每5轮对话）

### 5. Smart Context Compression
**文件**: chat.py
**实现**:
- 历史对话自动摘要（保留关键信息）
- 重要消息标记（工具调用结果）
- 压缩时优先保留重要消息

### 6. Memory System (长期记忆)
**文件**: 新建 memory.py
**实现**:
- 提取对话中的重要信息
- 存储到SQLite memory表
- 新会话自动召回相关记忆

## 实现顺序
1. 先实现Token-based管理（影响核心逻辑）
2. 工具结果摘要（减少token消耗）
3. 持久化存储（实用功能）
4. Checkpoint系统（高级功能）
5. Smart Compression（优化）
6. Memory系统（可选）

## 要求
- 保持类型注解完整
- 添加详细文档字符串
- 确保向后兼容
- 更新requirements.txt添加tiktoken
