import asyncio
import time

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


async def worker_task(worker_id, target_url, site_name):
    """工作任务函数"""
    mcp_url = "http://127.0.0.1:8000/mcp"

    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, call_back):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print(await session.list_tools())

            res = await session.call_tool("fetch_chunked", arguments={'url': target_url})
            print(res.content[0].text)

            """

            print(f"Worker {worker_id} ({site_name}) started")

            # 导航到指定网站
            res = await session.call_tool("navigate", arguments={'url': target_url})
            print(f"Worker {worker_id} ({site_name}) - Navigate result:")
            print(res.content[0].text)
            print('\n' * 3)

            # 点击链接
            # res = await session.call_tool("click_link", arguments={'link_number': "32"})
            # print(f"Worker {worker_id} ({site_name}) - Click link result:")
            # print(res.content[0].text)
            # print('\n' * 3)

            print(f"Worker {worker_id} ({site_name}) completed")
            
            """

async def main():
    # 创建4个并发任务，访问不同的网站
    tasks = [
        worker_task(1, "https://nyaa.si/", "Nyaa"),
        # worker_task(2, "https://www.baidu.com/", "Baidu"),
        # worker_task(3, "https://huggingface.co/models", "Hugging Face"),
        # worker_task(4, "https://www.google.com/", "Google")
    ]

    # 使用 asyncio.gather 并发执行
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())