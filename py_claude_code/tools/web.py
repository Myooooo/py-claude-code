"""Web 工具集.

包含网页获取和搜索功能.
适配国企内网/信创环境: 支持 HTTP/HTTPS 代理配置.
"""

import os
from typing import Any, Literal
from urllib.parse import urlparse
import httpx
from pydantic import Field, field_validator
from .base import BaseTool, ToolParameters, ToolResult, tool_registry


class WebFetchParams(ToolParameters):
    """网页获取参数."""

    url: str = Field(..., description="要获取的URL")
    method: Literal["GET", "POST"] = Field(default="GET", description="HTTP方法")
    headers: dict[str, str] | None = Field(
        default=None,
        description="自定义请求头"
    )
    timeout: int = Field(
        default=30,
        description="超时时间(秒)",
        ge=1,
        le=300
    )
    max_length: int = Field(
        default=100000,
        description="最大返回字符数",
        ge=1000,
        le=500000
    )
    format: Literal["markdown", "text", "html", "json"] = Field(
        default="markdown",
        description="输出格式: markdown(转换为Markdown), text(纯文本), html(原始HTML), json(JSON解析)"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """验证URL格式."""
        if not v or not v.strip():
            raise ValueError("URL不能为空")
        v = v.strip()

        # 自动添加协议
        if not v.startswith(("http://", "https://")):
            v = "https://" + v

        # 基本格式验证
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"无效的URL格式: {v}")

        return v


class WebSearchParams(ToolParameters):
    """网页搜索参数."""

    query: str = Field(..., description="搜索关键词")
    engine: Literal["bing", "google", "duckduckgo"] = Field(
        default="bing",
        description="搜索引擎"
    )
    max_results: int = Field(
        default=10,
        description="最大返回结果数",
        ge=1,
        le=20
    )
    timeout: int = Field(
        default=30,
        description="超时时间(秒)",
        ge=1,
        le=120
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """验证搜索词."""
        if not v or not v.strip():
            raise ValueError("搜索关键词不能为空")
        return v.strip()


def get_proxy_config() -> str | None:
    """获取代理配置（适配内网环境）.

    按以下优先级读取代理设置:
    1. CLAUDE_HTTP_PROXY / CLAUDE_HTTPS_PROXY 环境变量
    2. HTTP_PROXY / HTTPS_PROXY 环境变量
    3. http_proxy / https_proxy 环境变量（小写）
    4. 无代理

    返回: 代理 URL 字符串，供 httpx.AsyncClient 使用
    """
    # HTTPS 代理优先
    proxy = (
        os.environ.get("CLAUDE_HTTPS_PROXY") or
        os.environ.get("HTTPS_PROXY") or
        os.environ.get("https_proxy")
    )

    if not proxy:
        # 回退到 HTTP 代理
        proxy = (
            os.environ.get("CLAUDE_HTTP_PROXY") or
            os.environ.get("HTTP_PROXY") or
            os.environ.get("http_proxy")
        )

    return proxy


def html_to_markdown(html: str, url: str) -> str:
    """将 HTML 转换为 Markdown.

    使用简单正则实现，避免依赖外部库（适配内网环境）.
    """
    import re

    text = html

    # 移除 script 和 style 标签及其内容
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 移除注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # 提取标题
    title_match = re.search(r'<title[^>]*>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    # 转换标题标签
    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<h5[^>]*>(.*?)</h5>', r'##### \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<h6[^>]*>(.*?)</h6>', r'###### \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)

    # 转换段落和换行
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # 转换链接
    text = re.sub(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f'[{m.group(2).strip()}]({m.group(1)})',
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # 转换粗体和斜体
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)

    # 转换代码
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```\n', text, flags=re.IGNORECASE | re.DOTALL)

    # 转换列表
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<ul[^>]*>(.*?)</ul>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<ol[^>]*>(.*?)</ol>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)

    # 移除其他 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)

    # 解码 HTML 实体
    import html
    text = html.unescape(text)

    # 清理多余空白
    text = re.sub(r'\n\n\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # 组合标题和内容
    result = ""
    if title:
        result += f"# {title}\n\n"
    result += f"**来源:** {url}\n\n"
    result += text.strip()

    return result


def html_to_text(html: str) -> str:
    """将 HTML 转换为纯文本."""
    import re
    import html as html_module

    text = html

    # 移除 script 和 style
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 转换换行标签
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)

    # 移除所有标签
    text = re.sub(r'<[^>]+>', ' ', text)

    # 解码实体
    text = html_module.unescape(text)

    # 清理空白
    text = re.sub(r'\n\n\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    return text.strip()


class WebFetchTool(BaseTool):
    """网页获取工具.

    适用场景：
    - 获取技术文档内容
    - 读取内网 Wiki 或知识库
    - 获取 API 文档
    - 抓取网页数据进行分析

    内网环境配置：
    通过环境变量配置代理（如需要）：
    - CLAUDE_HTTP_PROXY=http://proxy.company.com:8080
    - CLAUDE_HTTPS_PROXY=http://proxy.company.com:8080

    特点：
    - 支持 HTTP/HTTPS 代理
    - 自动 HTML 转 Markdown（无需外部依赖）
    - 支持响应长度限制
    - 超时保护
    """

    name: str = "web_fetch"
    description: str = """获取网页内容并转换为可读格式.

使用场景：
- 获取技术文档（如内网 Wiki、知识库）
- 读取 API 文档页面
- 抓取网页数据进行摘要分析
- 访问内网系统页面

参数说明：
- url: 网页地址（支持 http/https，可省略协议头）
- method: HTTP 方法（默认 GET）
- format: 输出格式（markdown/text/html/json）
- max_length: 最大字符数（默认 10万字符）
- timeout: 超时时间（默认 30 秒）

代理配置（内网环境）：
设置环境变量 CLAUDE_HTTP_PROXY 和 CLAUDE_HTTPS_PROXY

示例：
- 获取文档: {"url": "https://docs.python.org/3/library/asyncio.html"}
- 获取内网: {"url": "http://wiki.company.com/api-guide", "format": "text"}
- 带认证: {"url": "https://api.example.com/docs", "headers": {"Authorization": "Bearer xxx"}}"""

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        max_length: int = 100000,
        format: str = "markdown",
        **kwargs: Any
    ) -> ToolResult:
        """执行网页获取."""
        try:
            # 获取代理配置
            proxy = get_proxy_config()

            # 构建客户端
            client_kwargs = {
                "timeout": httpx.Timeout(timeout),
                "follow_redirects": True,
            }
            if proxy:
                client_kwargs["proxy"] = proxy

            # 默认请求头
            default_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            }
            if headers:
                default_headers.update(headers)

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=default_headers
                )

                # 检查状态码
                if response.status_code >= 400:
                    return ToolResult.failure(
                        f"HTTP {response.status_code}: 请求失败",
                        status_code=response.status_code,
                        url=url
                    )

                content_type = response.headers.get("content-type", "").lower()

                # 根据格式处理响应
                if format == "json" or "application/json" in content_type:
                    try:
                        data = response.json()
                        import json
                        content = json.dumps(data, ensure_ascii=False, indent=2)
                        content_type = "json"
                    except Exception:
                        content = response.text
                        content_type = "text"

                elif format == "html":
                    content = response.text
                    content_type = "html"

                elif format == "text":
                    content = html_to_text(response.text)
                    content_type = "text"

                else:  # markdown (default)
                    content = html_to_markdown(response.text, url)
                    content_type = "markdown"

                # 截断过长的内容
                truncated = False
                original_length = len(content)
                if len(content) > max_length:
                    content = content[:max_length]
                    content += f"\n\n[内容已截断，原始长度 {original_length} 字符]"
                    truncated = True

                # 生成摘要
                summary = content[:500].replace('\n', ' ')
                if len(content) > 500:
                    summary += "..."

                return ToolResult.ok(
                    content,
                    url=url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=len(content),
                    original_length=original_length,
                    truncated=truncated,
                    summary=summary,
                    headers=dict(response.headers)
                )

        except httpx.TimeoutException:
            return ToolResult.failure(
                f"请求超时 ({timeout}秒)",
                url=url,
                timeout=timeout
            )

        except httpx.ProxyError as e:
            return ToolResult.failure(
                f"代理错误: {e}. 请检查 CLAUDE_HTTP_PROXY/CLAUDE_HTTPS_PROXY 配置",
                url=url,
                proxy_config=proxy if 'proxy' in dir() else None
            )

        except httpx.ConnectError as e:
            return ToolResult.failure(
                f"连接失败: {e}. 请检查网络连接或代理配置",
                url=url
            )

        except Exception as e:
            return ToolResult.failure(f"获取网页失败: {e}", url=url)

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return WebFetchParams.model_json_schema()


class WebSearchTool(BaseTool):
    """网页搜索工具.

    适用场景：
    - 搜索技术文档
    - 查找解决方案
    - 了解开源项目

    注意：
    - 需要访问外部搜索引擎 API
    - 在完全隔离的内网环境可能无法使用
    - 支持 Bing/Google API

    内网适配：
    - 通过 CLAUDE_HTTP_PROXY 配置代理
    - 可配置自建搜索引擎 API
    """

    name: str = "web_search"
    description: str = """使用搜索引擎查询网页.

使用场景：
- 搜索技术问题解决方案
- 查找开源项目文档
- 了解最新技术动态
- 搜索代码示例

支持的搜索引擎：
- bing: Bing Search API (默认)
- google: Google Custom Search API

环境变量配置：
- BING_API_KEY: Bing 搜索 API 密钥
- GOOGLE_API_KEY: Google API 密钥
- GOOGLE_CX: Google 搜索引擎 ID
- CLAUDE_HTTP_PROXY: HTTP 代理（内网环境）

注意：
- 需要外部网络访问权限
- 需要配置对应的 API 密钥
- 在内网隔离环境可能无法使用

示例：
- 搜索: {"query": "Python asyncio 教程"}
- Bing: {"query": "Docker 安装", "engine": "bing"}
- 限制: {"query": "Linux 命令", "max_results": 5}"""

    async def execute(
        self,
        query: str,
        engine: str = "bing",
        max_results: int = 10,
        timeout: int = 30,
        **kwargs: Any
    ) -> ToolResult:
        """执行网页搜索."""
        try:
            # 获取代理配置
            proxy = get_proxy_config()

            client_kwargs = {
                "timeout": httpx.Timeout(timeout),
            }
            if proxy:
                client_kwargs["proxy"] = proxy

            async with httpx.AsyncClient(**client_kwargs) as client:
                if engine == "bing":
                    results = await self._search_bing(client, query, max_results)
                elif engine == "google":
                    results = await self._search_google(client, query, max_results)
                else:
                    return ToolResult.failure(f"不支持的搜索引擎: {engine}")

                if not results:
                    return ToolResult.ok(
                        f"未找到关于 '{query}' 的搜索结果",
                        query=query,
                        engine=engine,
                        results=[]
                    )

                # 格式化输出
                lines = [f"🔍 搜索结果: '{query}'", f"引擎: {engine}", ""]

                for i, result in enumerate(results, 1):
                    lines.append(f"{i}. {result['title']}")
                    lines.append(f"   {result['url']}")
                    if result.get('snippet'):
                        snippet = result['snippet'].replace('\n', ' ')
                        lines.append(f"   {snippet}")
                    lines.append("")

                return ToolResult.ok(
                    "\n".join(lines),
                    query=query,
                    engine=engine,
                    results=results,
                    count=len(results)
                )

        except Exception as e:
            return ToolResult.failure(f"搜索失败: {e}", query=query, engine=engine)

    async def _search_bing(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int
    ) -> list[dict]:
        """Bing 搜索."""
        api_key = os.environ.get("BING_API_KEY")

        if not api_key:
            # 模拟搜索结果（无 API 密钥时）
            return [{
                "title": "[需要配置 BING_API_KEY 环境变量]",
                "url": "https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview",
                "snippet": "请设置 BING_API_KEY 环境变量以启用 Bing 搜索功能。"
            }]

        endpoint = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        params = {
            "q": query,
            "count": min(max_results, 50),
            "mkt": "zh-CN"
        }

        response = await client.get(endpoint, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        web_pages = data.get("webPages", {}).get("value", [])

        results = []
        for page in web_pages[:max_results]:
            results.append({
                "title": page.get("name", ""),
                "url": page.get("url", ""),
                "snippet": page.get("snippet", ""),
                "date": page.get("dateLastCrawled", "")
            })

        return results

    async def _search_google(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int
    ) -> list[dict]:
        """Google 搜索."""
        api_key = os.environ.get("GOOGLE_API_KEY")
        cx = os.environ.get("GOOGLE_CX")

        if not api_key or not cx:
            # 模拟搜索结果
            return [{
                "title": "[需要配置 GOOGLE_API_KEY 和 GOOGLE_CX]",
                "url": "https://developers.google.com/custom-search/v1/overview",
                "snippet": "请设置 GOOGLE_API_KEY 和 GOOGLE_CX 环境变量以启用 Google 搜索。"
            }]

        endpoint = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max_results, 10)
        }

        response = await client.get(endpoint, params=params)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        results = []
        for item in items[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        return results

    def get_parameters_schema(self) -> dict[str, Any]:
        """获取参数 schema."""
        return WebSearchParams.model_json_schema()


# 注册工具
tool_registry.register(WebFetchTool())
tool_registry.register(WebSearchTool())
