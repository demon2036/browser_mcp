#!/usr/bin/env python3
"""Browser MCP Server - Complete Implementation with Closure Pattern"""
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Dict, List, Any, Callable, Optional
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, ContentBlock
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from browser import BrowserManager, create_browser_tools

logger = logging.getLogger(__name__)


# ========== Generic MCP Server ==========

class GenericMCPServer:
    """Generic MCP server that can be used for any tools"""

    def __init__(
            self,
            name: str,
            port: int = 8000,
            init_func: Optional[Callable] = None,
            cleanup_func: Optional[Callable] = None
    ):
        self.name = name
        self.port = port
        self.server = Server(name)
        self._tools: List[Dict[str, Any]] = []
        self._init_func = init_func
        self._cleanup_func = cleanup_func

        self._setup_handlers()

    def _setup_handlers(self):
        """Setup MCP protocol handlers"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name=tool['name'],
                    description=tool['description'],
                    inputSchema=tool['schema']
                )
                for tool in self._tools
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[ContentBlock]:
            # Find tool
            tool = next((t for t in self._tools if t['name'] == name), None)
            if not tool:
                raise ValueError(f"Unknown tool: {name}")

            # Get context and call handler
            ctx = self.server.request_context
            result = await tool['handler'](ctx, arguments)

            # Wrap result as ContentBlock
            if isinstance(result, str):
                return [TextContent(type="text", text=result)]
            elif isinstance(result, list):
                return result
            else:
                return [TextContent(type="text", text=str(result))]

    def register_tools(self, tools: List[Dict[str, Any]]):
        """Register tool configurations"""
        self._tools.extend(tools)
        logger.info(f"Registered {len(tools)} tools: {[t['name'] for t in tools]}")

    def create_app(self) -> Starlette:
        """Create ASGI app with StreamableHTTP transport"""
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            event_store=None,
            json_response=False,
            stateless=False
        )

        async def handle_mcp(scope: Scope, receive: Receive, send: Send):
            await session_manager.handle_request(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            async with session_manager.run():
                # Run initialization
                if self._init_func:
                    await self._init_func()

                logger.info(f"🚀 {self.name} started on http://localhost:{self.port}/mcp")

                try:
                    yield
                finally:
                    logger.info("👋 Shutting down...")
                    if self._cleanup_func:
                        await self._cleanup_func()

        return Starlette(
            routes=[Mount("/mcp", app=handle_mcp)],
            lifespan=lifespan
        )

    def run(self):
        """Run the server"""
        app = self.create_app()
        uvicorn.run(app, host="127.0.0.1", port=self.port, log_level="info")

# ========== Main Entry Point ==========

def main():
    """Main function"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create browser manager
    browser_manager = BrowserManager(max_sessions=64, headless=True)

    # Create server with lifecycle functions
    server = GenericMCPServer(
        name='browser-control',
        port=8000,
        init_func=lambda: browser_manager.initialize(),
        cleanup_func=lambda: browser_manager.close()
    )

    # Register browser tools (browser_manager is bound via closure)
    server.register_tools(create_browser_tools(browser_manager))

    # Run server
    server.run()


if __name__ == "__main__":
    main()