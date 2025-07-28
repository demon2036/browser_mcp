import asyncio
import time

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    mcp_url = "http://127.0.0.1:8000/mcp"

    async with streamablehttp_client(mcp_url) as (read_stream, write_stream,call_back):
        async with ClientSession(read_stream, write_stream,) as session:
            await session.initialize()
            for i in range(1):
                res = await session.call_tool("navigate",arguments={'url':"https://www.baidu.com/"})
                print(res.content[0].text)
                print('\n'*5)

                res = await session.call_tool("click_link", arguments={'link_number': "32"})
                print(res.content[0].text)



if __name__ == "__main__":
    asyncio.run(main())
