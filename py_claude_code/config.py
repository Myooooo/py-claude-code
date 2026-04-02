"""配置管理模块."""

import os
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file_paths() -> list[str]:
    """获取可能的 .env 文件路径列表."""
    paths = []
    
    # 1. 当前工作目录
    paths.append(".env")
    
    # 2. 项目根目录（与 config.py 同级）
    project_root = Path(__file__).parent
    paths.append(str(project_root / ".env"))
    
    # 3. 父目录（如果从模块内运行）
    parent_dir = project_root.parent
    if (parent_dir / ".env").exists():
        paths.append(str(parent_dir / ".env"))
    
    return paths


class Config(BaseSettings):
    """应用配置类."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI API配置
    api_key: str = Field(..., description="OpenAI API Key")
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API Base URL"
    )
    model: str = Field(
        default="gpt-4o",
        description="使用的模型名称"
    )

    # 应用配置
    max_tokens: int = Field(
        default=4096,
        description="最大生成token数"
    )
    temperature: float = Field(
        default=0.7,
        description="采样温度"
    )
    max_context_messages: int = Field(
        default=50,
        description="最大上下文消息数（已废弃，使用max_context_tokens）"
    )
    max_context_tokens: int = Field(
        default=100000,
        description="最大上下文token数"
    )
    enable_tool_summarization: bool = Field(
        default=True,
        description="是否启用工具结果自动摘要"
    )
    enable_session_persistence: bool = Field(
        default=True,
        description="是否启用会话持久化存储"
    )
    session_db_path: str = Field(
        default=".claude_sessions.db",
        description="会话数据库存储路径"
    )
    max_tool_iterations: int = Field(
        default=10,
        description="最大工具调用迭代次数"
    )

    # UI配置
    theme: str = Field(
        default="monokai",
        description="代码高亮主题"
    )
    code_width: int = Field(
        default=120,
        description="代码显示宽度"
    )

    # 系统提示词
    system_prompt: str = Field(
        default="""你是一个专业的编程助手，名为 Claude Code Python版。
你可以帮助用户完成各种编程任务，包括：
- 读取、写入和编辑文件
- 执行 Bash 命令
- 搜索文件内容
- 查看目录结构

使用工具时请注意：
1. 读取文件前先确认文件存在
2. 编辑文件时确保提供正确的 old_string 和 new_string
3. 执行命令时注意安全性，避免删除重要文件
4. 处理大文件时考虑分批处理

请始终保持专业和友好的态度。""",
        description="系统提示词"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """验证API Key不为空."""
        if not v or not v.strip():
            raise ValueError("API Key 不能为空")
        return v.strip()

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """验证temperature在有效范围内."""
        if not 0 <= v <= 2:
            raise ValueError("temperature 必须在 0-2 之间")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """验证max_tokens为正整数."""
        if v < 1:
            raise ValueError("max_tokens 必须为正整数")
        return v

    def get_headers(self) -> dict[str, str]:
        """获取API请求头."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


def _load_env_file() -> None:
    """从可能的位置加载 .env 文件到环境变量."""
    from dotenv import load_dotenv
    
    env_paths = get_env_file_paths()
    for env_path in env_paths:
        path = Path(env_path)
        if path.exists():
            load_dotenv(dotenv_path=path, override=True)
            return  # 只加载第一个找到的


def load_config() -> Config:
    """加载配置，尝试从多个位置查找 .env 文件."""
    _load_env_file()
    return Config()


def get_default_config() -> Config:
    """获取默认配置（用于测试）."""
    return Config(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )
