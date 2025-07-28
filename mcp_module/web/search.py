import aiohttp
from typing import Dict, Any

# ========== 工具配置 ==========
SEARCH_TOOL_CONFIG = {
    'name': 'search',
    'description': '搜索网络内容',
    'schema': {
        'type': 'object',
        'properties': {
            'query': {
                'type': 'string',
                'description': '搜索关键词'
            },
            'max_results': {
                'type': 'integer',
                'description': '返回的最大结果数',
                'default': 5,
                'minimum': 1,
                'maximum': 20
            }
        },
        'required': ['query']
    },
    'hidden_params': {
        'searxng_url': 'http://localhost:8888'
    }
}


# ========== 异步搜索函数 ==========
async def searxng_search(query: str, searxng_url: str = "http://localhost:8888", max_results: int = 5) -> list:
    """异步 SearxNG 搜索"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{searxng_url}/search",
                    params={'q': query, 'format': 'json', 'categories': 'general', 'engines': '360search'},
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                data = await response.json()
                return [
                    {'title': item.get('title', ''), 'url': item.get('url', ''), 'snippet': item.get('content', '')}
                    for item in data.get('results', [])[:max_results]
                ]
    except Exception as e:
        return [{'error': str(e)}]


async def tavily_search(query: str, api_key: str, max_results: int = 5) -> list:
    """异步 Tavily 搜索"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query, "search_depth": "advanced", "max_results": max_results},
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                data = await response.json()
                return [
                    {'title': item.get('title', ''), 'url': item.get('url', ''), 'snippet': item.get('content', '')}
                    for item in data.get('results', [])
                ]
    except Exception as e:
        return [{'error': str(e)}]


# ========== 导出工具配置 ==========
def get_tool_config() -> Dict[str, Any]:
    """获取完整的工具配置"""
    return {
        **SEARCH_TOOL_CONFIG,
        'func': searxng_search
    }
