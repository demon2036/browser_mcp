#!/usr/bin/env python3
"""原生 MCP 服务器 - 使用 Streamable HTTP 传输"""
import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import List, Dict, Any, Optional

import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, ContentBlock
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# 导入工具配置
from mcp_module.web.search import get_tool_config as get_search_config
from mcp_module.web.fetch import (
    get_fetch_chunked_config,
    get_fetch_summary_config
)

logger = logging.getLogger(__name__)


class NativeMCPServer:
    """原生 MCP 服务器 - 完全控制 schema"""

    def __init__(
            self,
            name: str,
            port: int = 8000,
            json_response: bool = False,
            stateless: bool = True
    ):
        self.name = name
        self.port = port
        self.json_response = json_response
        self.stateless = stateless

        # 创建 MCP Server
        self.server = Server(name)
        self._tools_config: List[Dict[str, Any]] = []

        # 设置处理器
        self._setup_handlers()

    def _setup_handlers(self):
        """设置 MCP 处理器"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """列出所有工具"""
            tools = []
            for config in self._tools_config:
                tools.append(Tool(
                    name=config['name'],
                    description=config['description'],
                    inputSchema=config['schema']
                ))
            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[ContentBlock]:
            """调用工具"""
            # 查找工具配置
            config = next(
                (c for c in self._tools_config if c['name'] == name),
                None
            )
            if not config:
                raise ValueError(f"Unknown tool: {name}")

            # 合并隐藏参数
            func = config['func']
            hidden_params = config.get('hidden_params', {})
            full_args = {**hidden_params, **arguments}
            # 调用异步函数
            result = await func(**full_args)
            print(result)

            return [TextContent(type="text", text=result)]

    def register_tools(self, tools_config: List[Dict[str, Any]]):
        """注册工具配置

        Args:
            tools_config: [{
                'func': 异步函数对象,
                'name': 工具名称,
                'description': 描述,
                'schema': inputSchema (完全自定义),
                'hidden_params': 隐藏参数的默认值 dict
            }]
        """
        self._tools_config = tools_config
        logger.info(f"注册了 {len(tools_config)} 个工具")

    def create_app(self) -> Starlette:
        """创建 Starlette 应用"""
        # 创建 session manager
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            event_store=None,
            json_response=self.json_response,
            stateless=self.stateless,
        )

        async def handle_streamable_http(
                scope: Scope, receive: Receive, send: Send
        ) -> None:
            await session_manager.handle_request(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            """生命周期管理"""
            async with session_manager.run():
                logger.info(f"🚀 {self.name} MCP 服务器已启动 (Streamable HTTP)")
                logger.info(f"📍 监听地址: http://localhost:{self.port}/mcp")
                try:
                    yield
                finally:
                    logger.info("👋 服务器关闭中...")

        # 创建 Starlette 应用
        app = Starlette(
            debug=False,
            routes=[
                Mount("/mcp", app=handle_streamable_http),
            ],
            lifespan=lifespan,
        )

        return app

    def run(self):
        """运行服务器"""
        app = self.create_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建服务器
    server = NativeMCPServer(
        name="search-service",
        port=8001,
        json_response=False,  # 使用 SSE 流式响应
        stateless=True  # 无状态模式
    )

    # 注册工具 - 极简化
    server.register_tools([
        get_search_config(),
        # get_fetch_summary_config(),
        # get_fetch_summary_config()
    ])

    # 运行服务器
    server.run()