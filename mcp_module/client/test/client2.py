import asyncio
import time

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


async def worker_task(worker_id, target_url, site_name):
    """工作任务函数"""
    mcp_url = "http://0.0.0.0:8000/mcp"

    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, call_back):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print(await session.list_tools())

            res = await session.call_tool("navigate", arguments={"url": "https://browser.qq.com/mac"})
            print(res.content[0].text)
            res = await session.call_tool("click_element", arguments={"element_number": 7})
            print(res.content[0].text)


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