import asyncio
import time

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    mcp_url = "http://localhost:8000/mcp"

    async with streamablehttp_client(mcp_url) as (read_stream, write_stream,call_back):
        async with ClientSession(read_stream, write_stream,) as session:
            await session.initialize()

            for i in range(1):
                res = await session.call_tool("browser_navigate",
                                              {"url": "https://github.com/jlowin/fastmcp/blob/7ce0a59ea6959a73a46722e3e9884f7f13327072/docs/servers/proxy.mdx#L35"}
                                              )
                print(res)
                # 拼接所有文本块
                time.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
