#!/usr/bin/env python3
"""
代码审查系统 - 使用Gemini CLI进行Code Review
"""

import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

WORKSPACE = "/Users/fmy/.openclaw/workspace/code/py-claude-code"
LOG_DIR = Path(WORKSPACE) / "logs"
REVIEW_LOG = LOG_DIR / "gemini_reviews.txt"

def get_git_diff():
    """获取当前git变更"""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
    except:
        return ""

def get_all_files():
    """获取所有Python文件"""
    try:
        result = subprocess.run(
            ["find", WORKSPACE, "-name", "*.py", "-type", "f"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip().split('\n')
    except:
        return []

def review_file(file_path):
    """使用Gemini审查单个文件"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if len(content) > 10000:
            content = content[:10000] + "\n... (truncated)"
        
        prompt = f"""请审查以下Python代码文件，检查以下方面：
1. 代码质量和最佳实践
2. 潜在的错误或问题
3. 改进建议
4. 安全考虑

文件: {file_path}

代码内容:
```python
{content}
```

请提供简洁但全面的审查意见。"""
        
        result = subprocess.run(
            ["gemini", "--model", "gemini-2.5-pro-preview-03-25", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.stdout
    except Exception as e:
        return f"审查失败: {str(e)}"

def run_review():
    """运行完整审查"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 开始代码审查...")
    
    files = get_all_files()
    files = [f for f in files if f.strip() and not f.endswith('monitor.py') and not f.endswith('review.py')]
    
    if not files:
        print("  暂无文件需要审查")
        return
    
    print(f"  发现 {len(files)} 个Python文件")
    
    reviews = []
    for file_path in files:
        print(f"  正在审查: {Path(file_path).name}")
        review = review_file(file_path)
        reviews.append({
            "file": file_path,
            "review": review
        })
        time.sleep(2)  # 避免API限制
    
    # 保存审查结果
    with open(REVIEW_LOG, 'a') as f:
        f.write(f"\n\n{'='*60}\n")
        f.write(f"审查时间: {timestamp}\n")
        f.write(f"文件数量: {len(files)}\n")
        f.write(f"{'='*60}\n")
        
        for item in reviews:
            f.write(f"\n文件: {item['file']}\n")
            f.write("-" * 40 + "\n")
            f.write(item['review'])
            f.write("\n")
    
    print(f"  审查完成，结果已保存到: {REVIEW_LOG}")

if __name__ == "__main__":
    run_review()
