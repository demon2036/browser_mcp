#!/usr/bin/env python3
"""Browser MCP Server - Native implementation with flexible schema"""
import asyncio
import contextlib
import logging
from typing import List
from collections.abc import AsyncIterator

import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, ContentBlock
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from browser import BrowserManager

logger = logging.getLogger(__name__)


class BrowserMCPServer:
    """Native MCP Server for browser control with precise schema control"""

    def __init__(self, port: int = 8000, max_sessions: int = 16, headless: bool = False):
        self.port = port
        self.server = Server("browser-control")
        self.browser_manager = BrowserManager(max_sessions, headless)

        # Session mapping: MCP session ID -> browser session ID
        self._session_map = {}

        self._setup_handlers()

    def _get_browser_session_id(self, mcp_session_id: str) -> str:
        """Get or create browser session ID for MCP session"""
        if mcp_session_id not in self._session_map:
            self._session_map[mcp_session_id] = f"browser_{mcp_session_id}"
        return self._session_map[mcp_session_id]

    def _setup_handlers(self):
        """Setup MCP handlers with precise schema definitions"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="navigate",
                    description="Navigate to a URL and return page info with numbered links",
                    inputSchema={
                        "type": "object",
                        "required": ["url"],
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to navigate to",
                                "pattern": "^https?://",
                                "examples": ["https://example.com", "http://localhost:3000"]
                            }
                        },
                        "additionalProperties": False
                    }
                ),
                Tool(
                    name="click_link",
                    description="Click a link by its number from the previously loaded page",
                    inputSchema={
                        "type": "object",
                        "required": ["link_number"],
                        "properties": {
                            "link_number": {
                                "type": "integer",
                                "description": "The number of the link to click (1-based index)",
                                "minimum": 1,
                                "examples": [1, 2, 3]
                            }
                        },
                        "additionalProperties": False
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[ContentBlock]:
            """Execute browser tools with session isolation"""
            ctx = self.server.request_context

            # Get browser session ID from MCP session
            mcp_session_id = str(id(ctx.session))
            browser_session_id = self._get_browser_session_id(mcp_session_id)

            if name == "navigate":
                result = await self.browser_manager.navigate(
                    arguments["url"],
                    browser_session_id
                )
            elif name == "click_link":
                result = await self.browser_manager.click_link(
                    arguments["link_number"],
                    browser_session_id
                )
            else:
                raise ValueError(f"Unknown tool: {name}")

            # Format response
            if result["success"]:
                response = f"**{result['title']}**\n{result['url']}\n\n"
                if result.get("links"):
                    response += "**Available links:**\n"
                    for link in result["links"]:
                        response += f"{link['number']}. {link['text']}\n"
            else:
                response = f"❌ Error: {result['error']}"

            return [TextContent(type="text", text=response)]

    def create_app(self) -> Starlette:
        """Create Starlette app with StreamableHTTP transport"""
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            event_store=None,  # Stateless for simplicity
            json_response=False,  # Use SSE
            stateless=True
        )

        async def handle_mcp(scope: Scope, receive: Receive, send: Send):
            await session_manager.handle_request(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            async with session_manager.run():
                await self.browser_manager.initialize()
                logger.info(f"🌐 Browser MCP Server started on http://localhost:{self.port}/mcp")
                try:
                    yield
                finally:
                    logger.info("👋 Shutting down...")
                    await self.browser_manager.close()

        return Starlette(
            routes=[Mount("/mcp", app=handle_mcp)],
            lifespan=lifespan
        )

    def run(self):
        """Run the server"""
        app = self.create_app()
        uvicorn.run(app, host="0.0.0.0", port=self.port, log_level="info")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    server = BrowserMCPServer(port=8000, max_sessions=4, headless=False)
    server.run()