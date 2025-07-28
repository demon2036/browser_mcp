#!/usr/bin/env python3
"""Browser management module with session support and SOTA interactive element analysis."""
import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Any
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages browser sessions with LRU eviction and SOTA element tracking."""

    def __init__(self, max_sessions: int = 16, headless: bool = False):
        self.max_sessions = max_sessions
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.sessions: OrderedDict[str, Dict] = OrderedDict()
        self.session_links: Dict[str, Dict[int, str]] = {}  # Now stores xpath strings
        self._session_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the browser instance."""
        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            logger.info("Browser initialized")

    async def close(self):
        """Close all sessions and the browser."""
        async with self._session_lock:
            for session_data in self.sessions.values():
                try:
                    await session_data['page'].close()
                    await session_data['context'].close()
                except Exception as e:
                    logger.error(f"Error closing session: {e}")

            self.sessions.clear()
            self.session_links.clear()

        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_or_create_session(self, session_id: str) -> Page:
        """Get existing session or create a new one."""
        await self.initialize()

        async with self._session_lock:
            if session_id in self.sessions:
                self.sessions.move_to_end(session_id)
                return self.sessions[session_id]['page']

            # Evict LRU if at capacity
            if len(self.sessions) >= self.max_sessions:
                oldest_id, oldest_data = self.sessions.popitem(last=False)
                await oldest_data['page'].close()
                await oldest_data['context'].close()
                self.session_links.pop(oldest_id, None)
                logger.info(f"Evicted session: {oldest_id}")

            # Create new session
            context = await self.browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()
            self.sessions[session_id] = {'context': context, 'page': page}
            self.session_links[session_id] = {}
            logger.info(f"Created session: {session_id}")

            return page

    async def extract_and_store_links(self, page: Page, session_id: str) -> Dict:
        """Extract interactive elements using SOTA analysis."""
        try:
            index_js_content = Path("../index.js").read_text()

            result = await page.evaluate(f"""
                const analyzePage = {index_js_content};
                analyzePage({{
                    doHighlightElements: false,
                    focusHighlightIndex: -1,
                    viewportExpansion: 100,
                    debugMode: false
                }});
            """)

            # Extract interactive elements - direct copy from browser.py
            interactive = [node for _, node in result['map'].items()
                           if isinstance(node, dict) and node.get('isInteractive')]

            display_elements = []
            for i, node in enumerate(interactive):
                tag = node.get('tagName', 'element')
                text = ''

                # Get text from children
                if children := node.get('children'):
                    if child := result['map'].get(children[0]):
                        if child.get('type') == 'TEXT_NODE':
                            text = f" | {child.get('text', '')}"

                # Get href or class
                attrs = node.get('attributes', {})
                detail = attrs.get('href', '') or attrs.get('class', '')[:30]
                if detail:
                    detail = f" → {detail}"

                display_text = f"{tag}{detail}{text}"
                display_elements.append({
                    'xpath': node.get('xpath', ''),
                    'text': display_text[:200]
                })

            # Store mappings
            async with self._session_lock:
                self.session_links[session_id] = {}
                display_links = []

                for i, element in enumerate(display_elements, 1):
                    self.session_links[session_id][i] = element['xpath']
                    display_links.append({'number': i, 'text': element['text']})

            return {"success": True, "links": display_links}

        except Exception as e:
            logger.error(f"Error extracting elements: {e}")
            return {"success": False, "error": str(e)}

    async def navigate(self, url: str, session_id: str) -> Dict:
        """Navigate to URL and return page info with interactive elements."""
        try:
            page = await self.get_or_create_session(session_id)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            title = await page.title()
            current_url = page.url
            links_result = await self.extract_and_store_links(page, session_id)

            if not links_result["success"]:
                return links_result  # Return error from extract_and_store_links

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "links": links_result["links"]
            }
        except Exception as e:
            logger.error(f"Navigate error: {e}")
            return {"success": False, "error": str(e)}

    async def click_link(self, link_number: int, session_id: str) -> Dict:
        """Click an interactive element by its number using xpath."""
        try:
            async with self._session_lock:
                if session_id not in self.session_links:
                    return {"success": False, "error": "No active session"}

                if link_number not in self.session_links[session_id]:
                    max_link = len(self.session_links[session_id])
                    return {"success": False, "error": f"Invalid element number. Available: 1-{max_link}"}

                xpath = self.session_links[session_id][link_number]

            page = await self.get_or_create_session(session_id)
            await page.locator(f'xpath={xpath}').first.click()
            await page.wait_for_timeout(1000)

            title = await page.title()
            current_url = page.url
            links_result = await self.extract_and_store_links(page, session_id)

            if not links_result["success"]:
                return links_result  # Return error from extract_and_store_links

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "links": links_result["links"]
            }
        except Exception as e:
            logger.error(f"Click element error: {e}")
            return {"success": False, "error": str(e)}


# ========== Business Logic ==========

def format_browser_result(result: Dict[str, Any]) -> str:
    """Format browser result into readable text"""
    if result["success"]:
        response = f"**{result['title']}**\n{result['url']}\n\n"
        if result.get("links"):
            response += "**Available interactive elements:**\n"
            for link in result["links"]:
                response += f"{link['number']}. {link['text']}\n"
        return response
    else:
        return f"❌ Error: {result['error']}"


# ========== Browser Tool Builder ==========

def create_browser_tools(browser_manager: BrowserManager) -> List[Dict[str, Any]]:
    """Create browser tools with SOTA element interaction."""

    async def navigate(ctx, arguments: dict) -> str:
        """Navigate to URL"""
        session_id = str(id(ctx.session))
        result = await browser_manager.navigate(arguments["url"], session_id)
        return format_browser_result(result)

    async def click_element(ctx, arguments: dict) -> str:
        """Click interactive element by number"""
        session_id = str(id(ctx.session))
        result = await browser_manager.click_link(arguments["element_number"], session_id)
        return format_browser_result(result)

    return [
        {
            "name": "navigate",
            "description": "Navigate to a URL and analyze interactive elements",
            "schema": {
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
            },
            "handler": navigate
        },
        {
            "name": "click_element",
            "description": "Click an interactive element by its number",
            "schema": {
                "type": "object",
                "required": ["element_number"],
                "properties": {
                    "element_number": {
                        "type": "integer",
                        "description": "The number of the element to click (1-based index)",
                        "minimum": 1,
                        "examples": [1, 2, 3]
                    }
                },
                "additionalProperties": False
            },
            "handler": click_element
        }
    ]