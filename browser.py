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


async def get_file_metadata(url: str, page: Page = None) -> Dict:
    """Get file metadata without downloading the entire file"""
    try:
        # Try HEAD request first
        async with aiohttp.ClientSession() as session:
            try:
                async with session.head(url, allow_redirects=True) as response:
                    response.raise_for_status()

                    filename = extract_filename_from_headers(response.headers)
                    if not filename:
                        parsed_url = urlparse(url)
                        filename = unquote(parsed_url.path.split('/')[-1])
                        if not filename or filename.endswith('/'):
                            filename = 'download'
                            ext = get_extension_from_content_type(response.headers.get('content-type'))
                            if ext and not filename.endswith(ext):
                                filename += ext

                    return {
                        "filename": filename,
                        "url": url,
                        "size": int(response.headers.get('content-length', 0)),
                        "content_type": response.headers.get('content-type', 'unknown'),
                        "method": "head_request"
                    }
            except Exception as e:
                logger.info(f"HEAD request failed: {e}, trying partial GET")

                # Fallback to partial GET
                headers = {'Range': 'bytes=0-0'}
                async with session.get(url, headers=headers) as response:
                    if response.status == 206:  # Partial Content
                        content_range = response.headers.get('content-range', '')
                        size_match = re.search(r'/(\d+)$', content_range)
                        size = int(size_match.group(1)) if size_match else 0
                    else:
                        size = int(response.headers.get('content-length', 0))

                    filename = extract_filename_from_headers(response.headers)
                    if not filename:
                        parsed_url = urlparse(url)
                        filename = unquote(parsed_url.path.split('/')[-1])
                        if not filename or filename.endswith('/'):
                            filename = 'download'
                            ext = get_extension_from_content_type(response.headers.get('content-type'))
                            if ext and not filename.endswith(ext):
                                filename += ext

                    return {
                        "filename": filename,
                        "url": url,
                        "size": size,
                        "content_type": response.headers.get('content-type', 'unknown'),
                        "method": "partial_get"
                    }

    except Exception as e:
        logger.error(f"Failed to get file metadata: {e}")
        # Return basic info if metadata fetch fails
        parsed_url = urlparse(url)
        filename = unquote(parsed_url.path.split('/')[-1]) or 'download'
        return {
            "filename": filename,
            "url": url,
            "size": 0,
            "content_type": "unknown",
            "method": "fallback"
        }


class BrowserManager:
    """Manages browser sessions with LRU eviction and SOTA element tracking."""

    def __init__(self, max_sessions: int = 16, headless: bool = False):
        self.max_sessions = max_sessions
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.sessions: OrderedDict[str, Dict] = OrderedDict()
        self.session_links: Dict[str, Dict[int, str]] = {}
        self._session_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the browser instance."""
        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox'],

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
            context = await self.browser.new_context(
                proxy={'server':'https_proxy=http://127.0.0.1:8118'},
                viewport={"width": 1920, "height": 1080})
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
                    doHighlightElements: true,
                    focusHighlightIndex: -1,
                    viewportExpansion: 100,
                    debugMode: false
                }});
            """)

            # Extract interactive elements
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

            async def handle_download(download):
                nonlocal download_info
                # Get basic info from download event
                basic_info = {
                    "filename": download.suggested_filename,
                    "url": download.url,
                    "detected": True,
                    "status": "started",
                    "trigger": "navigation"
                }
                # Enrich with metadata
                metadata = await get_file_metadata(download.url, page)
                download_info = {**basic_info, **metadata}
                download_detected.set()
                logger.info(f"Download detected during navigation: {download.suggested_filename}")

            # Register download handler
            page.on("download", handle_download)

            # Check if URL looks like a direct download link
            is_likely_download = any(url.lower().endswith(ext) for ext in
                                     ['.dmg', '.exe', '.zip', '.pdf', '.doc', '.docx',
                                      '.xls', '.xlsx', '.ppt', '.pptx', '.rar', '.7z',
                                      '.tar', '.gz', '.iso', '.msi', '.deb', '.rpm'])

            navigation_error = None
            try:
                # Try to navigate
                await page.goto(url, wait_until="commit" if is_likely_download else "domcontentloaded")
            except Exception as e:
                navigation_error = e
                if "net::ERR_ABORTED" in str(e) or "Download is starting" in str(e):
                    logger.info(f"Navigation aborted due to download: {url}")
                    try:
                        await asyncio.wait_for(download_detected.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                else:
                    raise

            # Wait for potential download
            if not navigation_error and not download_info:
                try:
                    await asyncio.wait_for(download_detected.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    if not is_likely_download:
                        await page.wait_for_timeout(2000)

            # Remove download handler
            page.remove_listener("download", handle_download)

            # Handle direct download case
            if navigation_error and download_info:
                return {
                    "success": True,
                    "url": url,
                    "title": "Direct Download",
                    "links": [],
                    "download_info": download_info,
                    "action_type": "direct_download"
                }
            elif navigation_error:
                raise navigation_error

            # Normal page navigation
            title = await page.title()
            current_url = page.url

            # Extract links if not a download
            links = []
            if not download_info or not is_likely_download:
                links_result = await self.extract_and_store_links(page, session_id)
                if links_result["success"]:
                    links = links_result["links"]

            result = {
                "success": True,
                "url": current_url,
                "title": title,
                "links": links
            }

            # Add download info if detected
            if download_info:
                result["download_info"] = download_info
                if is_likely_download:
                    result["action_type"] = "direct_download"

            return result

        except Exception as e:
            logger.error(f"Navigate error: {e}")
            return {"success": False, "error": str(e)}

    async def click_link(self, link_number: int, session_id: str) -> Dict:
        """Click an interactive element with download detection."""
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

            async def handle_download(download):
                nonlocal download_info
                # Get basic info from download event
                basic_info = {
                    "filename": download.suggested_filename,
                    "url": download.url,
                    "detected": True,
                    "status": "started",
                    "trigger": "click"
                }
                # Enrich with metadata
                metadata = await get_file_metadata(download.url, page)
                download_info = {**basic_info, **metadata}
                download_detected.set()
                logger.info(f"Download detected from click: {download.suggested_filename}")

            page.on("download", handle_download)

            # Record pre-click state
            old_url = page.url
            old_title = await page.title()

            # Click element
            await page.locator(f'xpath={xpath}').first.click()

            # Wait for potential changes
            try:
                await asyncio.wait_for(download_detected.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                await page.wait_for_timeout(3000)

            # Remove download handler
            page.remove_listener("download", handle_download)

            # Determine action type
            new_url = page.url
            new_title = await page.title()

            metadata = await get_file_metadata(new_url, page)
            print(metadata)

            if download_info:
                action_type = "download"
            elif new_url != old_url or new_title != old_title:
                action_type = "navigation"
            else:
                action_type = "no_change"

            # Re-analyze page elements
            links_result = await self.extract_and_store_links(page, session_id)
            if not links_result["success"]:
                return links_result

            result = {
                "success": True,
                "action_type": action_type,
                "url": new_url,
                "title": new_title,
                "links": links_result["links"]
            }

            # Add download info if detected
            if download_info:
                result["download_info"] = download_info

            return result

        except Exception as e:
            logger.error(f"Click element error: {e}")
            return {"success": False, "error": str(e)}

    async def force_download(self, url: str, session_id: str = None) -> Dict:
        """Get file metadata without downloading the entire file"""
        try:
            page = await self.get_or_create_session(session_id or "download_session")

            # Get metadata
            metadata = await get_file_metadata(url, page)

            # Build download_info
            download_info = {
                **metadata,
                "detected": True,
                "status": "metadata_only",
                "trigger": "force"
            }

            return {
                "success": True,
                "download_info": download_info,
                "filepath": f"downloads/{download_info['filename']}"  # Virtual path for compatibility
            }

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
        """Get file metadata without downloading"""
        session_id = str(id(ctx.session))
        return await browser_manager.force_download(
            arguments["url"],
            session_id
        )

    return [
        {
            "name": "navigate",
            "description": "Navigate to a URL and analyze interactive elements. Returns download_info if download is detected.",
            "schema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to",
                        "pattern": "^https?://",
                        "examples": ["https://example.com", "https://example.com/file.dmg"]
                    }
                },
                "additionalProperties": False
            },
            "handler": navigate
        },
        {
            "name": "click_element",
            "description": "Click an interactive element. Returns download_info if download is triggered.",
            "schema": {
                "type": "object",
                "required": ["element_number"],
                "properties": {
                    "element_number": {
                        "type": "integer",
                        "description": "The number of the element to click",
                        "minimum": 1
                    }
                },
                "additionalProperties": False
            },
            "handler": click_element
        },
        # {
        #     "name": "force_download",
        #     "description": "Get file metadata without downloading. Always returns download_info.",
        #     "schema": {
        #         "type": "object",
        #         "required": ["url"],
        #         "properties": {
        #             "url": {
        #                 "type": "string",
        #                 "description": "The URL of the file",
        #                 "pattern": "^https?://"
        #             }
        #         },
        #         "additionalProperties": False
        #     },
        #     "handler": force_download
        # }
    ]