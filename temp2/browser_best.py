#!/usr/bin/env python3
"""Browser management module with session support and SOTA interactive element analysis."""
import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Any
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page
import aiohttp
import aiofiles
from urllib.parse import urlparse, unquote
import re

logger = logging.getLogger(__name__)


def extract_filename_from_headers(headers):
    """Extract filename from HTTP headers"""
    content_disposition = headers.get('content-disposition', '')
    if content_disposition:
        filename_match = re.search(r'filename[*]?=["\']?([^;"\']+)', content_disposition)
        if filename_match:
            return unquote(filename_match.group(1))
    return None


def get_extension_from_content_type(content_type):
    """Get file extension from content-type"""
    mime_map = {
        'application/pdf': '.pdf',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'text/html': '.html',
        'text/plain': '.txt',
        'application/zip': '.zip',
        'application/json': '.json',
        'application/xml': '.xml',
    }
    if content_type:
        base_type = content_type.split(';')[0].strip()
        return mime_map.get(base_type, '')
    return ''


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
            context = await self.browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()
            self.sessions[session_id] = {'context': context, 'page': page}
            self.session_links[session_id] = {}
            logger.info(f"Created session: {session_id}")

            return page

    async def extract_and_store_links(self, page: Page, session_id: str) -> Dict:
        """Extract interactive elements using SOTA analysis."""
        try:
            index_js_content = Path("index.js").read_text()

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
        """Navigate to URL and return page info with interactive elements and download detection."""
        try:
            page = await self.get_or_create_session(session_id)

            # Setup download detection
            download_info = None
            download_detected = asyncio.Event()
            navigation_error = None

            def handle_download(download):
                nonlocal download_info
                download_info = {
                    "filename": download.suggested_filename,
                    "url": download.url,
                    "detected": True,
                    "status": "started",
                    "trigger": "navigation"
                }
                download_detected.set()
                logger.info(f"Download detected during navigation: {download.suggested_filename}")

            # Register download handler
            page.on("download", handle_download)

            # Check if URL looks like a direct download link
            is_likely_download = any(url.lower().endswith(ext) for ext in
                                     ['.dmg', '.exe', '.zip', '.pdf', '.doc', '.docx',
                                      '.xls', '.xlsx', '.ppt', '.pptx', '.rar', '.7z',
                                      '.tar', '.gz', '.iso', '.msi', '.deb', '.rpm'])

            try:
                # Try to navigate to the URL
                if is_likely_download:
                    # For likely downloads, don't wait for domcontentloaded
                    await page.goto(url, wait_until="commit")
                else:
                    await page.goto(url, wait_until="domcontentloaded")

            except Exception as e:
                navigation_error = e
                # Check if it's a download-related error
                if "net::ERR_ABORTED" in str(e) or "Download is starting" in str(e):
                    logger.info(f"Navigation aborted due to download: {url}")
                    # Wait a bit for download to be detected
                    try:
                        await asyncio.wait_for(download_detected.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                else:
                    # Re-raise if it's not a download-related error
                    raise

            # If not a download error, wait for page to settle or download
            if not navigation_error:
                try:
                    await asyncio.wait_for(download_detected.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    # No download detected in 2 seconds, continue normally
                    if not is_likely_download:
                        await page.wait_for_timeout(2000)

            # Remove download handler to avoid memory leaks
            page.remove_listener("download", handle_download)

            # Handle the case where navigation failed but download was detected
            if navigation_error and download_info:
                return {
                    "success": True,
                    "url": url,
                    "title": "Direct Download",
                    "links": [],
                    "download_info": download_info,
                    "description": "Direct download link - file download started successfully.",
                    "action_type": "direct_download"
                }
            elif navigation_error:
                # Navigation failed and no download detected
                raise navigation_error

            # Normal page navigation
            title = await page.title()
            current_url = page.url

            # Only extract links if we actually loaded a page
            if not download_info or not is_likely_download:
                links_result = await self.extract_and_store_links(page, session_id)
                if not links_result["success"]:
                    # If link extraction fails, still return success if we got the page
                    links = []
                else:
                    links = links_result["links"]
            else:
                links = []

            result = {
                "success": True,
                "url": current_url,
                "title": title,
                "links": links
            }

            # Add download info if detected
            if download_info:
                result["download_info"] = download_info
                result["description"] = "Navigation completed with automatic download detected."
                if is_likely_download:
                    result["action_type"] = "direct_download"
            else:
                result["description"] = "Navigation completed successfully."

            return result

        except Exception as e:
            logger.error(f"Navigate error: {e}")
            return {"success": False, "error": str(e)}

    async def click_link(self, link_number: int, session_id: str) -> Dict:
        """Click an interactive element with SOTA download detection."""
        try:
            async with self._session_lock:
                if session_id not in self.session_links:
                    return {"success": False, "error": "No active session"}

                if link_number not in self.session_links[session_id]:
                    max_link = len(self.session_links[session_id])
                    return {"success": False, "error": f"Invalid element number. Available: 1-{max_link}"}

                xpath = self.session_links[session_id][link_number]

            page = await self.get_or_create_session(session_id)

            # Setup download detection
            download_info = None
            download_detected = asyncio.Event()

            def handle_download(download):
                nonlocal download_info
                download_info = {
                    "filename": download.suggested_filename,
                    "url": download.url,
                    "detected": True,
                    "status": "started",
                    "trigger": "click"
                }
                download_detected.set()
                logger.info(f"Download detected from click: {download.suggested_filename}")

            page.on("download", handle_download)

            # Record pre-click state
            old_url = page.url
            old_title = await page.title()

            # Click element
            await page.locator(f'xpath={xpath}').first.click()

            # Wait for potential changes (download or navigation)
            try:
                await asyncio.wait_for(download_detected.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                # No download detected, wait for potential navigation
                await page.wait_for_timeout(3000)

            # Remove download handler
            page.remove_listener("download", handle_download)

            # Determine what happened
            new_url = page.url
            new_title = await page.title()

            if download_info:
                action_type = "download"
                description = "Download triggered successfully. Page remained unchanged but browser detected file download."
            elif new_url != old_url or new_title != old_title:
                action_type = "navigation"
                description = "Click triggered page navigation."
            else:
                action_type = "no_change"
                description = "Click completed but no page change or download detected. Element may be inactive or action failed."

            # Re-analyze page elements
            links_result = await self.extract_and_store_links(page, session_id)

            if not links_result["success"]:
                return links_result

            return {
                "success": True,
                "action_type": action_type,
                "description": description,
                "download_info": download_info,
                "url": new_url,
                "title": new_title,
                "links": links_result["links"]
            }

        except Exception as e:
            logger.error(f"Click element error: {e}")
            return {"success": False, "error": str(e)}

    async def force_download(self, url: str, filename: str = None, session_id: str = None) -> Dict:
        """Force download a file from URL"""
        try:
            download_dir = Path("./downloads")
            download_dir.mkdir(exist_ok=True)

            # Try direct HTTP download first
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        response.raise_for_status()

                        # Auto-detect filename if not provided
                        if not filename:
                            filename = extract_filename_from_headers(response.headers)
                            if not filename:
                                parsed_url = urlparse(url)
                                filename = unquote(parsed_url.path.split('/')[-1])
                                if not filename or filename.endswith('/'):
                                    filename = 'download'
                                    ext = get_extension_from_content_type(response.headers.get('content-type'))
                                    if ext and not filename.endswith(ext):
                                        filename += ext

                        filepath = download_dir / filename
                        content = await response.read()
                        async with aiofiles.open(filepath, 'wb') as f:
                            await f.write(content)

                        return {
                            "success": True,
                            "method": "direct_http",
                            "filepath": str(filepath),
                            "filename": filename,
                            "size": len(content),
                            "content_type": response.headers.get('content-type', 'unknown')
                        }
            except Exception as e:
                logger.info(f"Direct download failed: {e}, trying browser method")

            # Fallback to browser download
            page = await self.get_or_create_session(session_id or "download_session")

            if not filename:
                parsed_url = urlparse(url)
                filename = unquote(parsed_url.path.split('/')[-1]) or 'download'

            filepath = download_dir / filename

            # Try browser fetch
            try:
                await page.goto('about:blank')
                result = await page.evaluate('''
                    async (url) => {
                        try {
                            const response = await fetch(url);
                            const blob = await response.blob();
                            const buffer = await blob.arrayBuffer();
                            return {
                                success: true,
                                data: Array.from(new Uint8Array(buffer)),
                                type: blob.type,
                                size: blob.size
                            };
                        } catch (error) {
                            return {success: false, error: error.message};
                        }
                    }
                ''', url)

                if result["success"]:
                    filepath.write_bytes(bytes(result["data"]))
                    return {
                        "success": True,
                        "method": "browser_fetch",
                        "filepath": str(filepath),
                        "filename": filename,
                        "size": result['size'],
                        "content_type": result['type']
                    }
            except Exception as e:
                logger.info(f"Browser fetch failed: {e}")

            # Final attempt: navigate directly
            try:
                response = await page.goto(url, wait_until="networkidle")
                if response:
                    body = await response.body()
                    filepath.write_bytes(body)
                    return {
                        "success": True,
                        "method": "browser_navigation",
                        "filepath": str(filepath),
                        "filename": filename,
                        "size": len(body),
                        "content_type": response.headers.get('content-type', 'unknown')
                    }
            except Exception as e:
                logger.error(f"All download methods failed: {e}")

            return {"success": False, "error": "All download methods failed"}

        except Exception as e:
            logger.error(f"Force download error: {e}")
            return {"success": False, "error": str(e)}


# ========== Browser Tool Builder ==========

def create_browser_tools(browser_manager: BrowserManager) -> List[Dict[str, Any]]:
    """Create browser tools with SOTA element interaction."""

    async def navigate(ctx, arguments: dict) -> Dict:
        """Navigate to URL with download detection"""
        session_id = str(id(ctx.session))
        return await browser_manager.navigate(arguments["url"], session_id)

    async def click_element(ctx, arguments: dict) -> Dict:
        """Click interactive element by number with download detection"""
        session_id = str(id(ctx.session))
        return await browser_manager.click_link(arguments["element_number"], session_id)

    async def force_download(ctx, arguments: dict) -> Dict:
        """Force download a file"""
        session_id = str(id(ctx.session))
        return await browser_manager.force_download(
            arguments["url"],
            arguments.get("filename"),
            session_id
        )

    return [
        {
            "name": "navigate",
            "description": "Navigate to a URL and analyze interactive elements. Handles both regular pages and direct download links. Detects automatic downloads triggered by navigation.",
            "schema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to (can be a webpage or direct download link)",
                        "pattern": "^https?://",
                        "examples": ["https://example.com", "http://localhost:3000", "https://example.com/file.dmg"]
                    }
                },
                "additionalProperties": False
            },
            "handler": navigate
        },
        {
            "name": "click_element",
            "description": "Click an interactive element by its number with download detection",
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
        },
        {
            "name": "force_download",
            "description": "Force download a file from URL. Automatically detects filename from headers or URL. Uses multiple download strategies to handle different file types and CORS restrictions.",
            "schema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the file to download",
                        "pattern": "^https?://",
                        "examples": ["https://example.com/file.pdf", "https://example.com/image.png"]
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename. If not provided, will be auto-detected from headers or URL",
                        "examples": ["custom_name.pdf", "download.png"]
                    }
                },
                "additionalProperties": False
            },
            "handler": force_download
        }
    ]