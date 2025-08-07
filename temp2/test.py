#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import re

browser = None
context = None
page = None
session_links = {}


async def navigate(url):
    """导航到URL并提取可交互元素"""
    global browser, context, page, session_links

    if not browser:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            accept_downloads=True,
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
        )

        # 添加初始化脚本来隐藏自动化特征
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = {
                runtime: {}
            };
        """)

        page = await context.new_page()

    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # 执行元素分析
    index_js = Path("index.js").read_text()
    result = await page.evaluate(f"""
        const analyzePage = {index_js};
        analyzePage({{
            doHighlightElements: false,
            focusHighlightIndex: -1,
            viewportExpansion: 100,
            debugMode: false
        }});
    """)

    # 提取可交互元素
    interactive = [node for _, node in result['map'].items()
                   if isinstance(node, dict) and node.get('isInteractive')]

    links = []
    session_links.clear()

    for i, node in enumerate(interactive, 1):
        tag = node.get('tagName', 'element')
        text = ''

        if children := node.get('children'):
            if child := result['map'].get(children[0]):
                if child.get('type') == 'TEXT_NODE':
                    text = f" | {child.get('text', '')}"

        attrs = node.get('attributes', {})
        detail = attrs.get('href', '') or attrs.get('class', '')[:30]
        if detail:
            detail = f" → {detail}"

        display_text = f"{i}. {tag}{detail}{text}"[:200]
        links.append(display_text)
        session_links[i] = node.get('xpath', '')

    return {
        "url": page.url,
        "title": await page.title(),
        "links": links
    }


async def click_element(element_number):
    """点击指定编号的元素"""
    if element_number not in session_links:
        return {"error": f"无效元素编号，可用范围：1-{len(session_links)}"}

    xpath = session_links[element_number]
    download_info = None
    download_urls = []

    # 监听所有页面的下载事件
    async def handle_download(download):
        nonlocal download_info
        download_info = {
            "filename": download.suggested_filename,
            "url": download.url
        }
        print(f"\n🔽 检测到下载: {download.suggested_filename}")
        print(f"   下载URL: {download.url}")
        # 保存文件
        await download.save_as(f"/tmp/{download.suggested_filename}")
        print(f"   已保存到: /tmp/{download.suggested_filename}")

    # 监听网络响应
    async def handle_response(response):
        url = response.url
        if any(ext in url.lower() for ext in ['.dmg', '.exe', '.zip', '.pkg']) or 'download' in url.lower():
            if 'trace.qq.com' not in url:  # 排除跟踪请求
                download_urls.append(url)
                print(f"\n📡 检测到下载URL: {url}")

    # 监听新页面
    async def handle_page(new_page):
        print(f"\n🔄 新页面打开: {new_page.url}")
        new_page.on("download", handle_download)
        new_page.on("response", handle_response)

        # 等待新页面可能的下载
        await new_page.wait_for_timeout(3000)

    # 设置监听器
    page.on("download", handle_download)
    page.on("response", handle_response)
    context.on("page", handle_page)

    # 记录当前页面数
    pages_before = len(context.pages)

    # 打印点击前的元素信息
    element = page.locator(f'xpath={xpath}').first
    print(f"\n准备点击元素 #{element_number}: {xpath}")
    try:
        text = await element.inner_text()
        print(f"元素文本: {text}")
    except:
        pass

    # 点击元素
    await element.click()
    print("等待响应...")
    await page.wait_for_timeout(5000)

    # 检查新页面
    if len(context.pages) > pages_before:
        new_pages = context.pages[pages_before:]
        for new_page in new_pages:
            print(f"\n检查新页面: {new_page.url}")

            # 尝试从新页面提取下载链接
            try:
                # 查找所有链接
                links = await new_page.locator('a[href*=".dmg"], a[href*="download"]').all()
                for link in links:
                    href = await link.get_attribute('href')
                    if href and '.dmg' in href:
                        print(f"找到下载链接: {href}")
                        download_urls.append(href)
            except:
                pass

    # 如果没有自动下载，尝试其他方法
    if not download_info and not download_urls:
        print("\n尝试执行页面JavaScript获取下载链接...")
        try:
            # 尝试获取页面中的下载链接
            download_url = await page.evaluate("""
                () => {
                    // 查找包含下载链接的元素
                    const links = document.querySelectorAll('a[href*=".dmg"], a[href*="download"]');
                    for (let link of links) {
                        if (link.href && link.href.includes('.dmg')) {
                            return link.href;
                        }
                    }

                    // 检查是否有下载相关的全局变量
                    if (window.downloadUrl) return window.downloadUrl;
                    if (window.download_url) return window.download_url;
                    if (window.macDownloadUrl) return window.macDownloadUrl;

                    // 查找onclick中的下载链接
                    const elements = document.querySelectorAll('[onclick*="download"], [onclick*=".dmg"]');
                    for (let el of elements) {
                        const match = el.onclick.toString().match(/(https?:\/\/[^\s'"]+\.dmg)/);
                        if (match) return match[1];
                    }

                    return null;
                }
            """)

            if download_url:
                print(f"从页面提取到下载链接: {download_url}")
                download_urls.append(download_url)
        except Exception as e:
            print(f"JavaScript执行失败: {e}")

    # 清理监听器
    page.remove_listener("download", handle_download)
    page.remove_listener("response", handle_response)
    context.remove_listener("page", handle_page)

    # 如果捕获到下载URL但没有触发下载，尝试直接下载
    if not download_info and download_urls:
        print(f"\n未触发标准下载，尝试直接访问下载链接...")
        for url in download_urls:
            if '.dmg' in url:
                try:
                    print(f"尝试下载: {url}")
                    # 创建新页面访问下载链接
                    download_page = await context.new_page()
                    download_page.on("download", handle_download)

                    await download_page.goto(url)
                    await download_page.wait_for_timeout(3000)

                    if not download_info:
                        # 如果还是没有下载，使用fetch获取
                        print("使用page.evaluate下载...")
                        await download_page.evaluate(f"""
                            (url) => {{
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = url.split('/').pop();
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                            }}
                        """, url)
                        await download_page.wait_for_timeout(3000)

                    await download_page.close()
                    if download_info:
                        break
                except Exception as e:
                    print(f"下载失败: {e}")

    # 重新分析页面
    result = await navigate(page.url)

    response = {
        "action_type": "download" if download_info else "no_download",
        "url": result["url"],
        "title": result["title"],
        "links": result["links"]
    }

    if download_info:
        response["download_info"] = download_info
    elif download_urls:
        response["download_urls"] = download_urls
        print(f"\n⚠️  捕获到{len(download_urls)}个下载链接但未能自动下载")
        print("你可以手动下载这些链接：")
        for url in download_urls:
            if '.dmg' in url:
                print(f"  wget '{url}'")

    return response


async def main():
    # 导航到QQ浏览器Mac页面
    res = await navigate("https://aqllq.sengfeng.cn/channel_4.html?wordId=1170163895025&creativeid=123115745105&bfsemuserid=17022&pid=sembd102615&bd_vid=11092662730189734840")
    print(f"页面: {res['title']}")
    print(f"找到 {len(res['links'])} 个可交互元素\n")
    for link in res['links'][:20]:
        print(link)

    # 点击第7个元素（立即下载）
    print("\n点击元素 #7...")
    res = await click_element(7)
    print(f"\n操作类型: {res['action_type']}")
    print(f"当前页面: {res['title']}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())