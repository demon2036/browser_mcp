#!/usr/bin/env python3
"""Session-aware MCP Browser Server with navigation, click support, and link extraction."""
import asyncio
import logging
from collections import OrderedDict
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger(__name__)


class SessionBrowserServer:
    def __init__(self, max_sessions=16, headless=False):
        self.mcp = FastMCP('session-browser')
        self.browser = None
        self.playwright = None
        self.sessions = OrderedDict()
        self.max_sessions = max_sessions
        self.headless = headless
        # Store link mappings for each session
        self.session_links = {}

        # Register tools
        self.mcp.tool()(self.navigate)
        self.mcp.tool()(self.click)
        self.mcp.tool()(self.click_link)
        self.mcp.tool()(self.get_page_state)

    async def get_browser(self):
        """Initialize browser if not already running"""
        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            logger.info("Browser initialized")
        return self.browser

    async def _evict_lru_session(self):
        """Evict least recently used session when limit reached"""
        if not self.sessions:
            return

        session_id, session_data = self.sessions.popitem(last=False)
        try:
            await session_data['page'].close()
            await session_data['context'].close()
            # Clean up link mappings
            if session_id in self.session_links:
                del self.session_links[session_id]
            logger.info(f"Evicted session: {session_id}")
        except Exception as e:
            logger.error(f"Error evicting session: {e}")

    async def get_session_context(self, session_id):
        """Get or create a browser session for the given session ID"""
        # Return existing session
        if session_id in self.sessions:
            self.sessions.move_to_end(session_id)
            return self.sessions[session_id]['context'], self.sessions[session_id]['page']

        # Evict LRU if at capacity
        if len(self.sessions) >= self.max_sessions:
            await self._evict_lru_session()

        # Create new session
        browser = await self.get_browser()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        self.sessions[session_id] = {'context': context, 'page': page}
        self.session_links[session_id] = {}
        logger.info(f"Created session: {session_id}")

        return context, page

    async def extract_and_store_links(self, page: Page, session_id: str):
        """Extract all links from the page and store mappings"""
        try:
            # JavaScript to extract all links
            links_data = await page.evaluate('''() => {
                const links = [];
                const anchors = document.querySelectorAll('a[href]');
                const seen = new Set();

                anchors.forEach((el) => {
                    const href = el.getAttribute('href');
                    const text = (el.innerText || el.textContent || '').trim();

                    // Skip empty text links or duplicates
                    if (!text) return;

                    // Create absolute URL
                    let absoluteUrl;
                    try {
                        absoluteUrl = new URL(href, window.location.origin).href;
                    } catch {
                        absoluteUrl = href;
                    }

                    // Create unique key for deduplication
                    const key = text + '|' + absoluteUrl;
                    if (!seen.has(key)) {
                        seen.add(key);
                        links.push({
                            text: text.substring(0, 200), // Limit text length
                            url: absoluteUrl,
                            selector: `a[href="${href}"]`
                        });
                    }
                });

                return links;
            }''')

            # Clear previous links for this session
            self.session_links[session_id] = {}

            # Store links with numbers and create display list
            display_links = []
            for i, link in enumerate(links_data, 1):
                # Store the mapping
                self.session_links[session_id][i] = {
                    'url': link['url'],
                    'selector': link['selector']
                }

                # Add to display list (only number and text)
                display_links.append({
                    'number': i,
                    'text': link['text']
                })

            logger.info(f"Extracted {len(display_links)} links for session {session_id}")
            return display_links

        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            return []

    async def navigate(self, url: str, ctx: Context):
        """Navigate to a URL in the session's browser context and return numbered links"""
        try:
            session_id = str(id(ctx.session))
            context, page = await self.get_session_context(session_id)

            # Navigate with smart waiting
            await page.goto(url, wait_until="domcontentloaded")

            # Try to wait for network idle
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except:
                # Some pages never reach networkidle
                pass

            title = await page.title()
            current_url = page.url

            # Extract and store links
            display_links = await self.extract_and_store_links(page, session_id)

            return {
                "success": True,
                "session_id": session_id,
                "url": current_url,
                "title": title,
                "links": display_links
            }

        except Exception as e:
            logger.error(f"Navigate error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def click(self, selector: str, ctx: Context):
        """Click an element on the page using CSS selector"""
        try:
            session_id = str(id(ctx.session))
            context, page = await self.get_session_context(session_id)

            # Wait for element and click
            element = await page.wait_for_selector(selector, timeout=10000)
            if not element:
                return {
                    "success": False,
                    "error": f"Element not found: {selector}"
                }

            await element.click()

            # Wait for potential navigation
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            # Extract new links after click
            display_links = await self.extract_and_store_links(page, session_id)

            return {
                "success": True,
                "session_id": session_id,
                "selector": selector,
                "url": page.url,
                "links": display_links
            }

        except Exception as e:
            logger.error(f"Click error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def click_link(self, link_number: int, ctx: Context):
        """Click a link by its number"""
        try:
            session_id = str(id(ctx.session))

            # Check if session exists
            if session_id not in self.session_links:
                return {
                    "success": False,
                    "error": "No active session. Please navigate to a URL first."
                }

            # Check if link number exists
            if link_number not in self.session_links[session_id]:
                return {
                    "success": False,
                    "error": f"Link number {link_number} not found. Available links: 1-{len(self.session_links[session_id])}"
                }

            context, page = await self.get_session_context(session_id)

            # Get link info
            link_info = self.session_links[session_id][link_number]

            # Navigate to the URL directly (more reliable than clicking)
            await page.goto(link_info['url'], wait_until="domcontentloaded")

            # Try to wait for network idle
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass

            title = await page.title()
            current_url = page.url

            # Extract new links after navigation
            display_links = await self.extract_and_store_links(page, session_id)

            return {
                "success": True,
                "session_id": session_id,
                "clicked_link": link_number,
                "url": current_url,
                "title": title,
                "links": display_links
            }

        except Exception as e:
            logger.error(f"Click link error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_page_state(self, ctx: Context):
        """Get the current page state including numbered links"""
        try:
            session_id = str(id(ctx.session))

            # Check if session exists
            if session_id not in self.sessions:
                return {
                    "success": False,
                    "error": "No active session. Please navigate to a URL first."
                }

            context, page = await self.get_session_context(session_id)

            # Get page info
            title = await page.title()
            current_url = page.url

            # Extract and store links
            display_links = await self.extract_and_store_links(page, session_id)

            return {
                "success": True,
                "session_id": session_id,
                "url": current_url,
                "title": title,
                "links": display_links
            }

        except Exception as e:
            logger.error(f"Get page state error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def run(self):
        """Run the MCP server"""
        self.mcp.run(transport="streamable-http")


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run server
    server = SessionBrowserServer(max_sessions=4, headless=False)
    server.run()