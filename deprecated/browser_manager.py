#!/usr/bin/env python3
"""
Browser Manager - Core browser automation functionality
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


@dataclass
class BrowserSession:
    """Represents a browser session"""
    session_id: str
    context: BrowserContext
    page: Page
    created_at: float
    last_activity: float


class BrowserManager:
    """Manages browser sessions with state persistence"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.sessions: Dict[str, BrowserSession] = {}

    async def initialize(self):
        """Initialize the browser instance"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        logger.info("Browser manager initialized")

    async def shutdown(self):
        """Shutdown browser and cleanup"""
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        logger.info("Browser manager shutdown")

    async def get_or_create_session(self, session_id: str) -> BrowserSession:
        """Get existing session or create new one"""
        # Return existing session
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.last_activity = time.time()
            return session

        # Create new session
        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        session = BrowserSession(
            session_id=session_id,
            context=context,
            page=page,
            created_at=time.time(),
            last_activity=time.time()
        )

        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")

        return session

    async def close_session(self, session_id: str):
        """Close a browser session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.page.close()
            await session.context.close()
            del self.sessions[session_id]
            logger.info(f"Closed session: {session_id}")

    async def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        """Navigate to a URL"""
        try:
            session = await self.get_or_create_session(session_id)
            print(self.sessions)

            # Navigate with smart waiting
            await session.page.goto(url, wait_until="domcontentloaded")

            # Wait for network to settle
            try:
                await session.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                # Some pages never reach networkidle, that's ok
                pass

            # Get page info
            title = await session.page.title()
            current_url = session.page.url

            return {
                "success": True,
                "url": current_url,
                "title": title
            }

        except Exception as e:
            logger.error(f"Navigate error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def click(self, session_id: str, selector: str) -> Dict[str, Any]:
        """Click an element"""
        try:
            session = await self.get_or_create_session(session_id)

            # Wait for element and click
            element = await session.page.wait_for_selector(selector, timeout=10000)
            if not element:
                return {
                    "success": False,
                    "error": f"Element not found: {selector}"
                }

            await element.click()

            # Wait for potential navigation
            try:
                await session.page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            return {
                "success": True,
                "selector": selector
            }

        except Exception as e:
            logger.error(f"Click error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def input_text(self, session_id: str, selector: str, text: str) -> Dict[str, Any]:
        """Input text into an element"""
        try:
            session = await self.get_or_create_session(session_id)

            # Wait for element
            element = await session.page.wait_for_selector(selector, timeout=10000)
            if not element:
                return {
                    "success": False,
                    "error": f"Element not found: {selector}"
                }

            # Clear and type
            await element.click()
            await element.clear()
            await element.type(text)

            return {
                "success": True,
                "selector": selector,
                "text": text
            }

        except Exception as e:
            logger.error(f"Input error: {e}")
            return {
                "success": False,
                "error": str(e)
            }