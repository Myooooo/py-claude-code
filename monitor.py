#!/usr/bin/env python3
"""
Claude Code & Gemini CLI 工作进度监控系统
每10分钟汇报一次工作进度
"""

import subprocess
import time
import json
import os
from datetime import datetime
from pathlib import Path

# 配置
REPORT_INTERVAL = 600  # 10分钟
WORKSPACE = "/Users/fmy/.openclaw/workspace/code/py-claude-code"
LOG_DIR = Path(WORKSPACE) / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 会话名称
TMUX_SESSIONS = {
    "claude": "py-claude-dev",
    "gemini": "gemini-review"
}

def capture_tmux_output(session_name, lines=50):
    """捕获tmux会话的输出"""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            all_lines = result.stdout.strip().split('\n')
            return '\n'.join(all_lines[-lines:])
        return f"[错误] 无法捕获 {session_name} 的输出 (code: {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"[超时] 捕获 {session_name} 输出超时"
    except Exception as e:
        return f"[异常] 捕获 {session_name} 失败: {str(e)}"

def check_session_alive(session_name):
    """检查tmux会话是否存活"""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False

def restart_claude_session():
    """重新启动Claude Code会话"""
    print(f"[{datetime.now()}] 重新启动Claude Code会话...")
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSIONS["claude"]], capture_output=True)
    time.sleep(1)
    subprocess.run([
        "tmux", "new-session", "-d", "-s", TMUX_SESSIONS["claude"],
        "-c", WORKSPACE
    ])
    # 启动Claude Code
    subprocess.run([
        "tmux", "send-keys", "-t", TMUX_SESSIONS["claude"],
        "claude --permission-mode bypassPermissions --print '继续开发py-claude-code项目'",
        "Enter"
    ])
    return "Claude Code 会话已重启"

def restart_gemini_session():
    """重新启动Gemini CLI会话"""
    print(f"[{datetime.now()}] 重新启动Gemini CLI会话...")
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSIONS["gemini"]], capture_output=True)
    time.sleep(1)
    subprocess.run([
        "tmux", "new-session", "-d", "-s", TMUX_SESSIONS["gemini"],
        "-c", WORKSPACE
    ])
    return "Gemini CLI 会话已重启"

def generate_report():
    """生成工作进度报告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = {
        "timestamp": timestamp,
        "sessions": {}
    }
    
    for name, session in TMUX_SESSIONS.items():
        alive = check_session_alive(session)
        report["sessions"][name] = {
            "alive": alive,
            "output": capture_tmux_output(session, 30) if alive else "会话已终止"
        }
    
    return report

def save_and_notify(report):
    """保存报告并发送通知"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"report_{timestamp}.json"
    
    with open(log_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 生成文本报告
    text_report = f"""
=== 工作进度报告 [{report['timestamp']}] ===

【Claude Code 状态】
状态: {'✅ 运行中' if report['sessions']['claude']['alive'] else '❌ 已终止'}
最近输出:
{report['sessions']['claude']['output'][:500]}

【Gemini CLI 状态】
状态: {'✅ 运行中' if report['sessions']['gemini']['alive'] else '❌ 已终止'}
最近输出:
{report['sessions']['gemini']['output'][:500]}

==================
"""
    
    # 写入文本日志
    text_log = LOG_DIR / f"report_{timestamp}.txt"
    with open(text_log, 'w') as f:
        f.write(text_report)
    
    # 打印到控制台
    print(text_report)
    
    return text_report

def monitor_loop():
    """主监控循环"""
    print(f"[{datetime.now()}] 监控系统启动...")
    print(f"工作目录: {WORKSPACE}")
    print(f"报告间隔: {REPORT_INTERVAL}秒")
    print("-" * 50)
    
    while True:
        try:
            # 检查并重启死去的会话
            for name, session in TMUX_SESSIONS.items():
                if not check_session_alive(session):
                    print(f"[{datetime.now()}] ⚠️ {name} 会话已死，正在重启...")
                    if name == "claude":
                        restart_claude_session()
                    else:
                        restart_gemini_session()
                    time.sleep(2)
            
            # 生成报告
            report = generate_report()
            save_and_notify(report)
            
            # 等待下一次报告
            time.sleep(REPORT_INTERVAL)
            
        except KeyboardInterrupt:
            print(f"\n[{datetime.now()}] 监控系统已停止")
            break
        except Exception as e:
            print(f"[{datetime.now()}] 监控异常: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    monitor_loop()
