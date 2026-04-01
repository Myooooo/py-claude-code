#!/usr/bin/env python3
"""
完整的Gemini代码审查脚本
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

WORKSPACE = "/Users/fmy/.openclaw/workspace/code/py-claude-code"
REPORT_FILE = Path(WORKSPACE) / "logs" / f"gemini_full_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

def get_all_python_files():
    """获取所有Python文件"""
    result = subprocess.run(
        ["find", f"{WORKSPACE}/py_claude_code", "-name", "*.py", "-type", "f"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split('\n') if f]

def read_file_content(filepath):
    """读取文件内容"""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def generate_review_prompt(files_content):
    """生成审查提示词"""
    prompt = """你是一位资深的Python代码审查专家。请对以下py-claude-code项目的代码进行全面审查。

## 项目概述
这是一个Python实现的Claude Code编程助手，兼容OpenAI Chat Completions API，支持多轮对话和工具调用。

## 审查文件

"""
    for filepath, content in files_content.items():
        filename = Path(filepath).name
        prompt += f"\n### {filename}\n```python\n{content[:3000]}\n```\n"
    
    prompt += """
## 审查要求

请从以下维度对每个文件进行评分（1-10分）并提供详细分析：

1. **代码质量** - 代码结构、可读性、可维护性
2. **类型安全** - 类型注解的完整性和准确性
3. **错误处理** - 异常处理的完善程度
4. **安全性** - 潜在的安全漏洞（如命令注入、路径遍历等）
5. **性能** - 代码效率优化
6. **文档** - 文档字符串的质量
7. **最佳实践** - 是否符合Python最佳实践

## 输出格式

请以Markdown格式输出：

```markdown
# 代码审查报告

## 总体评分: X/10

## 文件审查

### [文件名]
- **评分**: X/10
- **优点**: 
  - 优点1
  - 优点2
- **问题**: 
  - 问题1
  - 问题2
- **建议**: 
  - 建议1
  - 建议2

## 总体评价
[总体评价]

## 改进建议优先级
1. [高优先级]
2. [中优先级]
3. [低优先级]
```
"""
    return prompt

def main():
    """主函数"""
    print("获取所有Python文件...")
    files = get_all_python_files()
    print(f"找到 {len(files)} 个文件")
    
    # 读取文件内容
    files_content = {}
    for filepath in files:
        content = read_file_content(filepath)
        files_content[filepath] = content
        print(f"  ✓ {Path(filepath).name}")
    
    # 生成提示词
    prompt = generate_review_prompt(files_content)
    
    # 保存提示词（用于调试）
    prompt_file = Path(WORKSPACE) / "logs" / "review_prompt.txt"
    with open(prompt_file, 'w') as f:
        f.write(prompt)
    print(f"\n提示词已保存到: {prompt_file}")
    
    # 调用Gemini
    print("\n调用Gemini进行审查...")
    result = subprocess.run(
        ["gemini", prompt[:8000]],  # 限制长度
        capture_output=True,
        text=True,
        timeout=300
    )
    
    # 保存审查结果
    with open(REPORT_FILE, 'w') as f:
        f.write(result.stdout)
    
    print(f"\n审查报告已保存到: {REPORT_FILE}")
    print("\n审查结果:")
    print(result.stdout[:2000])

if __name__ == "__main__":
    main()
