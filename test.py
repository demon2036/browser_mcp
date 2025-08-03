# ========== 示例使用 ==========
from mcp_module.web.search import search

# ========== 示例使用 ==========
if __name__ == "__main__":
    import asyncio


    async def main():
        # 直接使用Google搜索（默认），API密钥会自动从环境变量读取
        results = await search(
            query="ぱんぱかカフぃR",
            max_results=3,
            google_api_key='b7521a1c6a1c397d19274ee1ff1f5ab9b86d2f69'
        )
        print(results)

        print("Google Search Results:")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Snippet: {result.get('snippet', 'No snippet')[:100]}...")
            print()


    asyncio.run(main())