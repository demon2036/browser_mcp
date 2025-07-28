#!/usr/bin/env python3
"""Browser Query MCP 服务器 - 获取并切分网页内容"""
from mcp.server.fastmcp import FastMCP
from playwright.sync_api import sync_playwright
from langchain.text_splitter import RecursiveCharacterTextSplitter


class MCPBrowserQueryServer:
    """MCP Browser Query 服务器 - 获取并智能切分网页内容"""

    def __init__(self, port: int = None, chunk_size: int = 2048):
        """初始化服务器

        Args:
            port: MCP 服务端口
            chunk_size: 文本块大小，默认 2048
        """
        self.chunk_size = chunk_size
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=0,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

        # 创建 MCP 实例
        if port:
            self.mcp = FastMCP('browser-query', port=port)
        else:
            self.mcp = FastMCP('browser-query')

        self._register_tools()

    def _register_tools(self):
        """注册 MCP 工具"""

        @self.mcp.tool()
        def fetch(url: str):
            """获取并切分网页内容

            Args:
                url: 网页 URL

            Returns:
                切分后的内容块，格式为 L0, L1, L2...
            """
            try:
                # 获取网页内容
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until='domcontentloaded')
                    content = page.inner_text('*')
                    browser.close()

                # 切分内容
                chunks = self.splitter.split_text(content)

                # 格式化输出
                formatted_chunks = []
                for i, chunk in enumerate(chunks):
                    formatted_chunks.append(f"L{i}\n{chunk}")

                return {
                    'url': url,
                    'total_chunks': len(chunks),
                    'chunk_size': self.chunk_size,
                    'content': '\n\n'.join(formatted_chunks)
                }

            except Exception as e:
                return {'error': str(e), 'url': url}

    def run(self):
        """运行 MCP 服务器"""
        self.mcp.run()


if __name__ == "__main__":
    # 创建并运行服务器
    server = MCPBrowserQueryServer(chunk_size=2048)
    server.run()