"""Web 工具单元测试.

测试 WebFetchTool 和 WebSearchTool.
注意：部分测试需要网络访问或 Mock.
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from py_claude_code.tools.web import (
    WebFetchTool,
    WebSearchTool,
    get_proxy_config,
    html_to_markdown,
    html_to_text,
)


class TestProxyConfig:
    """测试代理配置."""

    def test_no_proxy(self, monkeypatch):
        """测试无代理配置."""
        # 清除所有代理环境变量
        for key in ['CLAUDE_HTTP_PROXY', 'CLAUDE_HTTPS_PROXY', 'HTTP_PROXY',
                    'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            monkeypatch.delenv(key, raising=False)

        result = get_proxy_config()
        assert result is None

    def test_claude_proxy(self, monkeypatch):
        """测试 CLAUDE_ 前缀代理配置（优先 HTTPS）."""
        monkeypatch.setenv('CLAUDE_HTTP_PROXY', 'http://proxy.company.com:8080')
        monkeypatch.setenv('CLAUDE_HTTPS_PROXY', 'https://proxy.company.com:8080')

        result = get_proxy_config()
        assert result is not None
        # HTTPS 代理优先
        assert result == 'https://proxy.company.com:8080'

    def test_standard_proxy(self, monkeypatch):
        """测试标准代理环境变量."""
        monkeypatch.setenv('HTTP_PROXY', 'http://proxy.example.com:3128')
        monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.example.com:3128')

        result = get_proxy_config()
        assert result is not None
        assert 'proxy.example.com' in result


class TestHtmlConverters:
    """测试 HTML 转换器."""

    def test_html_to_text_basic(self):
        """测试基本 HTML 转文本."""
        html = "<html><body><h1>标题</h1><p>段落内容</p></body></html>"
        text = html_to_text(html)

        assert "标题" in text
        assert "段落内容" in text
        assert "<html>" not in text

    def test_html_to_text_with_script(self):
        """测试移除 script 标签."""
        html = """
        <html>
            <head><script>alert('xss')</script></head>
            <body><p>内容</p></body>
        </html>
        """
        text = html_to_text(html)

        assert "alert" not in text
        assert "xss" not in text
        assert "内容" in text

    def test_html_to_text_with_style(self):
        """测试移除 style 标签."""
        html = """
        <html>
            <head><style>body { color: red; }</style></head>
            <body><p>内容</p></body>
        </html>
        """
        text = html_to_text(html)

        assert "color: red" not in text
        assert "内容" in text

    def test_html_to_markdown_basic(self):
        """测试基本 HTML 转 Markdown."""
        html = """
        <html>
            <head><title>测试页面</title></head>
            <body>
                <h1>一级标题</h1>
                <p>这是一个<strong>重要</strong>的段落。</p>
                <h2>二级标题</h2>
                <ul>
                    <li>项目1</li>
                    <li>项目2</li>
                </ul>
            </body>
        </html>
        """
        md = html_to_markdown(html, "https://example.com")

        assert "# 测试页面" in md  # 标题
        assert "# 一级标题" in md
        assert "## 二级标题" in md
        assert "**重要**" in md  # 粗体
        assert "- 项目1" in md  # 列表
        assert "来源:" in md  # URL

    def test_html_to_markdown_links(self):
        """测试链接转换."""
        html = '<p>点击<a href="https://example.com">这里</a>访问。</p>'
        md = html_to_markdown(html, "https://test.com")

        assert "[这里](https://example.com)" in md

    def test_html_to_markdown_code(self):
        """测试代码转换."""
        html = '<p>使用<code>print()</code>函数。</p>'
        md = html_to_markdown(html, "https://test.com")

        assert "`print()`" in md


class TestWebFetchTool:
    """测试 WebFetchTool."""

    @pytest.fixture
    def tool(self):
        """创建工具实例."""
        return WebFetchTool()

    @pytest.mark.asyncio
    async def test_url_validation(self, tool):
        """测试 URL 验证 - 缺少协议自动添加."""
        # 通过参数验证器测试
        from py_claude_code.tools.web import WebFetchParams

        # 有效 URL
        params = WebFetchParams(url="example.com")
        assert params.url == "https://example.com"

        # 已有协议
        params = WebFetchParams(url="http://example.com")
        assert params.url == "http://example.com"

    @pytest.mark.asyncio
    async def test_fetch_success_markdown(self, tool):
        """测试成功获取并转换为 Markdown."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>标题</h1><p>内容</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(url="https://example.com")

            assert result.success is True
            assert result.data["status_code"] == 200
            assert "# 标题" in result.content
            assert "内容" in result.content

    @pytest.mark.asyncio
    async def test_fetch_success_json(self, tool):
        """测试获取 JSON."""
        mock_data = {"key": "value", "list": [1, 2, 3]}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(mock_data)
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(return_value=mock_data)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(
                url="https://api.example.com/data",
                format="json"
            )

            assert result.success is True
            assert result.data["content_type"] == "json"
            assert '"key": "value"' in result.content

    @pytest.mark.asyncio
    async def test_fetch_http_error(self, tool):
        """测试 HTTP 错误."""
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(url="https://example.com/notfound")

            assert result.success is False
            assert "404" in result.error

    @pytest.mark.asyncio
    async def test_fetch_timeout(self, tool):
        """测试超时错误."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(url="https://example.com", timeout=5)

            assert result.success is False
            assert "超时" in result.error
            assert result.data["timeout"] == 5

    @pytest.mark.asyncio
    async def test_content_truncation(self, tool):
        """测试内容截断."""
        # 创建长内容
        long_content = "A" * 200000

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = f"<html><body><p>{long_content}</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(
                url="https://example.com",
                max_length=50000
            )

            assert result.success is True
            assert result.data["truncated"] is True
            assert result.data["content_length"] <= 50000 + 100  # 允许一些额外内容


class TestWebSearchTool:
    """测试 WebSearchTool."""

    @pytest.fixture
    def tool(self):
        """创建工具实例."""
        return WebSearchTool()

    @pytest.mark.asyncio
    async def test_search_bing_no_api_key(self, tool, monkeypatch):
        """测试 Bing 搜索 - 无 API 密钥."""
        monkeypatch.delenv("BING_API_KEY", raising=False)

        result = await tool.execute(query="Python tutorial", engine="bing")

        # 应该返回配置提示
        assert result.success is True  # 技术上成功，但结果是提示
        assert "BING_API_KEY" in result.content or "需要配置" in result.content

    @pytest.mark.asyncio
    async def test_search_google_no_api_key(self, tool, monkeypatch):
        """测试 Google 搜索 - 无 API 密钥."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CX", raising=False)

        result = await tool.execute(query="Python tutorial", engine="google")

        # 应该返回配置提示
        assert result.success is True

    @pytest.mark.asyncio
    async def test_search_bing_success(self, tool, monkeypatch):
        """测试 Bing 搜索成功."""
        monkeypatch.setenv("BING_API_KEY", "test_key")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "webPages": {
                "value": [
                    {
                        "name": "Python 教程",
                        "url": "https://docs.python.org",
                        "snippet": "Python 官方文档"
                    },
                    {
                        "name": "Python 入门",
                        "url": "https://tutorial.python.org",
                        "snippet": "适合初学者的教程"
                    }
                ]
            }
        })

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(query="Python", engine="bing")

            assert result.success is True
            assert "Python 教程" in result.content
            assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_search_empty_results(self, tool, monkeypatch):
        """测试空搜索结果."""
        monkeypatch.setenv("BING_API_KEY", "test_key")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "webPages": {"value": []}
        })

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await tool.execute(query="xyz123nonexistent", engine="bing")

            assert result.success is True
            assert "未找到" in result.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
