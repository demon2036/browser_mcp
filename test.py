import asyncio

from mcp_module.web.fetch import fetch,fetch_summary



print(asyncio.run(fetch_summary('https://kamitsubaki.jp/event/artist/kaf/',query='电台节目数量',

api_base='https://ms-shpc7pdz-100034032793-sw.gw.ap-shanghai.ti.tencentcs.com/ms-shpc7pdz/v1'

                        )           ))