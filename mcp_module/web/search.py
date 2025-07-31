import aiohttp
import json
import os
from typing import Dict, Any, Optional

# 环境变量说明：
# GOOGLE_SEARCH_KEY - Google Serper API密钥
# TAVILY_API_KEY - Tavily API密钥

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
        'searxng_url': 'http://localhost:8988',
        'google_api_key': os.getenv('GOOGLE_SEARCH_KEY', None),
        'tavily_api_key': os.getenv('TAVILY_API_KEY', None),
        'engine': 'google'  # 默认使用google搜索引擎
    }
}


# ========== 异步搜索函数 ==========
async def google_search(query: str, api_key: str, max_results: int = 5) -> list:
    """异步 Google Serper 搜索"""
    try:
        url = 'https://google.serper.dev/search'
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json',
        }
        data = {
            "q": query,
            'num': max_results
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    url,
                    headers=headers,
                    data=json.dumps(data),
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                results = await response.json()

                # 提取organic搜索结果
                organic_results = results.get('organic', [])
                return [
                    {
                        'title': item.get('title', ''),
                        'url': item.get('link', ''),
                        'snippet': item.get('snippet', '')
                    }
                    for item in organic_results[:max_results]
                ]
    except Exception as e:
        return [{'error': f'Google search error: {str(e)}'}]


async def searxng_search(query: str, searxng_url: str = "http://localhost:8888", max_results: int = 5) -> list:
    """异步 SearxNG 搜索"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{searxng_url}/search",
                    params={'q': query, 'format': 'json', 'categories': 'general'},
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                data = await response.json()

                return [
                    {
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'snippet': item.get('content', '')
                    }
                    for item in data.get('results', [])[:max_results]
                ]
    except Exception as e:
        return [{'error': f'SearxNG search error: {str(e)}'}]


async def tavily_search(query: str, api_key: str, max_results: int = 5) -> list:
    """异步 Tavily 搜索"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": max_results
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                data = await response.json()
                return [
                    {
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'snippet': item.get('content', '')
                    }
                    for item in data.get('results', [])
                ]
    except Exception as e:
        return [{'error': f'Tavily search error: {str(e)}'}]


# ========== 统一搜索接口 ==========
async def search(query: str,
                 max_results: int = 5,
                 engine: str = 'google',
                 google_api_key: Optional[str] = None,
                 tavily_api_key: Optional[str] = None,
                 searxng_url: str = "http://localhost:8888") -> list:
    """
    统一的搜索接口，支持多个搜索引擎

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数
        engine: 搜索引擎类型 ('google', 'searxng', 'tavily')
        google_api_key: Google Serper API密钥（可选，默认从环境变量读取）
        tavily_api_key: Tavily API密钥（可选，默认从环境变量读取）
        searxng_url: SearxNG服务URL

    Returns:
        搜索结果列表
    """
    # 如果没有传入API密钥，使用配置中的值（已从环境变量读取）
    if google_api_key is None:
        google_api_key = SEARCH_TOOL_CONFIG['hidden_params']['google_api_key']
    if tavily_api_key is None:
        tavily_api_key = SEARCH_TOOL_CONFIG['hidden_params']['tavily_api_key']

    if engine == 'google':
        if not google_api_key:
            return [{'error': 'Google API key not provided'}]
        return await google_search(query, google_api_key, max_results)

    elif engine == 'searxng':
        return await searxng_search(query, searxng_url, max_results)

    elif engine == 'tavily':
        if not tavily_api_key:
            return [{'error': 'Tavily API key not provided'}]
        return await tavily_search(query, tavily_api_key, max_results)

    else:
        return [{'error': f'Unknown search engine: {engine}'}]


# ========== 导出工具配置 ==========
def get_tool_config() -> Dict[str, Any]:
    """获取完整的工具配置"""
    return {
        **SEARCH_TOOL_CONFIG,
        'func': search  # 使用统一的搜索接口
    }


