#!/bin/bash
# 自动进度报告脚本

WORKSPACE="/Users/fmy/.openclaw/workspace/code/py-claude-code"
LOG_FILE="$WORKSPACE/logs/progress.log"

while true; do
    echo "========== $(date) ==========" >> "$LOG_FILE"
    
    # 统计文件
    echo "【文件统计】" >> "$LOG_FILE"
    find "$WORKSPACE/py_claude_code" -name "*.py" -type f -exec ls -lh {} \; 2>/dev/null >> "$LOG_FILE"
    
    # 检查进程
    echo -e "\n【进程状态】" >> "$LOG_FILE"
    ps aux | grep -E "claude|gemini" | grep -v grep >> "$LOG_FILE"
    
    # Git状态
    echo -e "\n【Git状态】" >> "$LOG_FILE"
    cd "$WORKSPACE" && git status --short 2>/dev/null >> "$LOG_FILE"
    
    echo -e "\n" >> "$LOG_FILE"
    
    sleep 600  # 10分钟
done
