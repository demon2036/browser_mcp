#!/usr/bin/env python3
"""极简搜索 MCP 服务器"""
import requests
from mcp.server.fastmcp import FastMCP
from playwright.sync_api import sync_playwright


def searxng_search(query: str, searxng_url: str, max_results: int = 5) -> list:
    """SearxNG 搜索实现"""
    try:
        r = requests.get(
            f"{searxng_url}/search",
            params={'q': query, 'format': 'json', 'categories': 'general'},
            timeout=30
        )
        data = r.json()
        return [
            {
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('content', '')
            }
            for item in data.get('results', [])[:max_results]
        ]
    except Exception as e:
        return [{'error': str(e)}]


def tavily_search(query: str, api_key: str, max_results: int = 5) -> list:
    """Tavily 搜索实现"""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results
            },
            timeout=30
        )
        data = r.json()
        return [
            {
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('content', '')
            }
            for item in data.get('results', [])
        ]
    except Exception as e:
        return [{'error': str(e)}]


class MCPSearchServer:
    """MCP 搜索服务器 - 支持搜索和网页获取"""

    def __init__(
            self,
            search_engine: str = "tavily",
            searxng_url: str = "http://localhost:8888",
            tavily_api_key: str = "",
            port: int = None
    ):
        self.search_engine = search_engine
        self.searxng_url = searxng_url
        self.tavily_api_key = tavily_api_key

        # 创建 MCP 实例
        self.mcp = FastMCP('search', port=port if port else 8000)
        self._register_tools()

    def _register_tools(self):
        """注册 MCP 工具"""

        @self.mcp.tool()
        def search(query: str, max_results: int = 5):
            """搜索网络"""
            if self.search_engine == "searxng":
                return searxng_search(query, self.searxng_url, max_results)
            else:
                return tavily_search(query, self.tavily_api_key, max_results)

        @self.mcp.tool()
        def fetch(url: str):
            """获取网页文本内容"""
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until='domcontentloaded')
                    content = page.inner_text('*')
                    browser.close()
                    return {'url': url, 'content': content}
            except Exception as e:
                return {'error': str(e), 'url': url}

    def run(self):
        """运行 MCP 服务器"""
        self.mcp.run('streamable-http')


# 直接运行时的配置
if __name__ == "__main__":
    # 配置
    SEARCH_ENGINE = "tavily"  # "searxng" 或 "tavily"
    SEARXNG_URL = "http://localhost:8888"
    TAVILY_API_KEY = "your-tavily-api-key"

    # 创建并运行服务器
    server = MCPSearchServer(
        search_engine=SEARCH_ENGINE,
        searxng_url=SEARXNG_URL,
        tavily_api_key=TAVILY_API_KEY
    )
    server.run()

    print(1)
    server2 = MCPSearchServer(
        search_engine=SEARCH_ENGINE,
        searxng_url=SEARXNG_URL,
        tavily_api_key=TAVILY_API_KEY,
        port=8001
    )
    server2.run()