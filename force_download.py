#!/usr/bin/env python3
"""Force download test script for embedded content like PDFs and images"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import aiohttp
import aiofiles


def extract_filename_from_headers(headers):
    """从HTTP headers中提取文件名"""
    content_disposition = headers.get('content-disposition', '')
    if content_disposition:
        import re
        # 尝试匹配 filename="xxx" 或 filename*=UTF-8''xxx
        filename_match = re.search(r'filename[*]?=["\']?([^;"\']+)', content_disposition)
        if filename_match:
            filename = filename_match.group(1)
            # 处理URL编码的文件名
            from urllib.parse import unquote
            return unquote(filename)
    return None


def get_extension_from_content_type(content_type):
    """根据content-type获取文件扩展名"""
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
        # 移除参数部分 (如 "; charset=utf-8")
        base_type = content_type.split(';')[0].strip()
        return mime_map.get(base_type, '')
    return ''


async def download_with_aiohttp(url: str, filepath: Path = None):
    """使用 aiohttp 直接下载文件"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()

            # 如果没有提供filepath，尝试自动获取文件名
            if filepath is None:
                filename = extract_filename_from_headers(response.headers)
                if not filename:
                    # 从URL获取文件名
                    from urllib.parse import urlparse, unquote
                    parsed_url = urlparse(url)
                    filename = unquote(parsed_url.path.split('/')[-1])

                    # 如果还是没有文件名或只是路径，使用默认名称
                    if not filename or filename.endswith('/'):
                        filename = 'download'
                        # 添加扩展名
                        ext = get_extension_from_content_type(response.headers.get('content-type'))
                        if ext and not filename.endswith(ext):
                            filename += ext

                download_dir = Path("./downloads")
                download_dir.mkdir(exist_ok=True)
                filepath = download_dir / filename

            content = await response.read()
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(content)
            return len(content), response.headers.get('content-type', 'unknown'), filepath


async def force_download(url: str, filename: str = None):
    """强制下载内嵌显示的内容"""
    download_dir = Path("./downloads")
    download_dir.mkdir(exist_ok=True)

    # 首先尝试使用 aiohttp 直接下载
    try:
        print(f"正在下载 (直接HTTP): {url}")
        size, content_type, filepath = await download_with_aiohttp(url,
                                                                   None if not filename else download_dir / filename)
        print(f"✓ 下载成功: {filepath}")
        print(f"  文件大小: {size} bytes")
        print(f"  内容类型: {content_type}")
        return True
    except Exception as e:
        print(f"直接下载失败: {e}")
        print("尝试使用浏览器下载...")

    # 如果没有提供filename，从URL提取
    if not filename:
        from urllib.parse import urlparse, unquote
        parsed_url = urlparse(url)
        filename = unquote(parsed_url.path.split('/')[-1]) or 'download'

    filepath = download_dir / filename

    # 如果直接下载失败，使用 Playwright
    async with async_playwright() as p:
        # 配置浏览器以禁用 PDF 查看器
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-features=ChromePdfRenderer']
        )

        # 创建带下载处理的上下文
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1280, 'height': 720}
        )

        page = await context.new_page()

        try:
            # 对于 PDF，使用特殊处理
            download_promise = None
            if url.endswith('.pdf'):
                try:
                    # 监听下载事件
                    download_promise = asyncio.create_task(wait_for_download(page))

                    # 注入脚本强制下载 PDF
                    await page.goto('about:blank')
                    await page.evaluate('''
                        (url) => {
                            const link = document.createElement('a');
                            link.href = url;
                            link.download = url.split('/').pop();
                            link.target = '_blank';
                            document.body.appendChild(link);
                            link.click();
                        }
                    ''', url)

                    # 等待下载
                    download = await asyncio.wait_for(download_promise, timeout=10)
                    await download.save_as(filepath)
                    print(f"✓ 下载成功 (通过浏览器): {filepath}")
                    return True
                except asyncio.TimeoutError:
                    print("下载超时，尝试其他方法...")
                finally:
                    # 取消未完成的任务
                    if download_promise and not download_promise.done():
                        download_promise.cancel()
                        try:
                            await download_promise
                        except asyncio.CancelledError:
                            pass

            # 对于非 PDF 文件或 PDF 下载失败的情况
            try:
                # 使用页面评估下载
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
                            return {
                                success: false,
                                error: error.message
                            };
                        }
                    }
                ''', url)

                if result["success"]:
                    filepath.write_bytes(bytes(result["data"]))
                    print(f"✓ 下载成功 (Fetch API): {filepath}")
                    print(f"  文件大小: {result['size']} bytes")
                    print(f"  内容类型: {result['type']}")
                    return True
                else:
                    print(f"✗ Fetch API 失败: {result['error']}")

            except Exception as e:
                print(f"浏览器下载失败: {e}")

            # 最后的尝试：使用页面导航
            try:
                response = await page.goto(url, wait_until="networkidle")
                if response:
                    body = await response.body()
                    filepath.write_bytes(body)
                    print(f"✓ 下载成功 (页面导航): {filepath}")
                    print(f"  文件大小: {len(body)} bytes")
                    return True
            except Exception as nav_error:
                print(f"页面导航失败: {nav_error}")

        except Exception as e:
            print(f"✗ 浏览器错误: {e}")
            return False
        finally:
            await context.close()
            await browser.close()

    print(f"✗ 所有下载方法都失败了")
    return False


async def wait_for_download(page):
    """等待下载事件"""
    async with page.expect_download() as download_info:
        download = await download_info.value
        return download


async def download_with_requests_fallback(url: str, filepath: Path):
    """使用 requests 作为最后的备选方案"""
    import requests
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        filepath.write_bytes(response.content)
        return len(response.content), response.headers.get('content-type', 'unknown')
    except Exception as e:
        raise e


async def test_downloads():
    """测试不同类型的下载"""
    test_urls = [
        # PDF
        ("https://arxiv.org/pdf/1706.03762", "attention_paper.pdf"),
        ("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "dummy.pdf"),

        # 图片
        ("https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png", "google_logo.png"),
        ("https://httpbin.org/image/jpeg", "test.jpg"),

        # 其他
        ("https://httpbin.org/html", "test.html"),
        ("https://www.example.com", "example.html"),
    ]

    # 测试自动文件名识别
    print("=== 测试自动文件名识别 ===")
    auto_urls = [
        "https://arxiv.org/pdf/1706.03762",  # 应该识别为 1706.03762.pdf
        "https://httpbin.org/image/png",  # 应该根据content-type识别为 .png
        "https://www.example.com/",  # 应该使用 download.html
    ]

    for url in auto_urls:
        print(f"\n--- 自动识别文件名: {url} ---")
        await force_download(url)  # 不提供filename参数
        await asyncio.sleep(1)

    print("\n\n=== 手动指定文件名测试 ===")
    for url, filename in test_urls:
        print(f"\n--- 测试: {filename} ---")
        await force_download(url, filename)
        await asyncio.sleep(1)

    print("\n\n=== 下载结果汇总 ===")
    download_dir = Path("./downloads")
    if download_dir.exists():
        files = list(download_dir.glob("*"))
        if files:
            print(f"成功下载 {len(files)} 个文件:")
            for f in sorted(files):
                print(f"  - {f.name} ({f.stat().st_size} bytes)")
        else:
            print("没有成功下载任何文件")
    else:
        print("下载目录不存在")


if __name__ == "__main__":
    print("强制下载测试开始...\n")

    # 确保安装了必要的库
    try:
        import aiohttp
        import aiofiles
    except ImportError:
        print("请先安装必要的库:")
        print("pip install playwright aiohttp aiofiles requests")
        exit(1)

    asyncio.run(test_downloads())
    print("\n测试完成！检查 ./downloads 目录")