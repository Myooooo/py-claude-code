# 修复清单

## 问题 1: chat.py - _extract_memory 应该是 async
**位置**: chat.py 第 ~140 行
**问题**: `_extract_memory` 用 `def` 定义但被 `await` 调用
**修复**:
```python
# 改为 async def
async def _extract_memory(self, role: str, content: str) -> None:
```

## 问题 2: storage.py - datetime 导入问题
**位置**: storage.py 第 1 行和第 232 行
**问题**: `from datetime import datetime, timedelta` 导入后，`datetime.now()` 实际上调用的是模块的 now 方法，但正确用法应该是 datetime 类
**修复**: 确认导入正确即可，代码逻辑是对的

## 问题 3: memory.py - 不规范的 __import__
**位置**: memory.py 第 235 行
**问题**: `__import__("datetime")` 极不规范
**修复**: 改为直接使用 datetime
```python
from datetime import datetime, timedelta
# ...
cutoff = datetime.now() - timedelta(days=days)
```

## 问题 4: chat.py - 缺少导入
**位置**: chat.py 顶部
**问题**: 使用了 `uuid` 但没有导入
**修复**:
```python
import uuid
from typing import AsyncIterator, Optional
```

## 问题 5: token_manager.py - 简化 _init_encoder
**位置**: token_manager.py
**问题**: 重复尝试加载 cl100k_base
**修复**: 简化逻辑

## 问题 6: token_manager.py - 改进 _create_summary
**位置**: token_manager.py
**问题**: 仅保留前3条消息
**修复**: 改进摘要逻辑

---

执行顺序:
1. 修复 chat.py 的导入问题 (问题 4)
2. 修复 chat.py 的 async 问题 (问题 1)
3. 修复 memory.py 的导入问题 (问题 3)
4. 修复 token_manager.py 的问题 (问题 5, 6)
5. 运行测试验证
6. git commit
