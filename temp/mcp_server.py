#!/usr/bin/env python3
"""MCP Server orchestrator for browser functionality."""
import logging
from mcp_module.server.fastmcp import FastMCP, Context
from browser import BrowserManager


class MCPBrowserServer:
    """MCP Server that exposes browser functionality as tools."""

    def __init__(self, max_sessions: int = 16, headless: bool = False):
        self.mcp = FastMCP('session-browser')
        self.browser_manager = BrowserManager(max_sessions, headless)
        self._register_tools()

    def _register_tools(self):
        """Register browser functions as MCP tools."""

        @self.mcp.tool()
        async def navigate(url: str, ctx: Context):
            """Navigate to a URL and return page info with numbered links."""
            session_id = str(id(ctx.session))
            result = await self.browser_manager.navigate(url, session_id)
            return result

        @self.mcp.tool()
        async def click_link(link_number: int, ctx: Context):
            """Click a link by its number."""
            session_id = str(id(ctx.session))
            result = await self.browser_manager.click_link(link_number, session_id)
            return result

    def run(self):
        """Run the MCP server."""
        self.mcp.run(transport="streamable-http")



def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    server = MCPBrowserServer(max_sessions=4, headless=False)
    server.run()


if __name__ == '__main__':
    main()