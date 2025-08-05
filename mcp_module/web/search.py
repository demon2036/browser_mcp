import aiohttp
import os
from typing import Dict, Any
from async_lru import alru_cache

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
            }
        },
        'required': ['query']
    },
    'hidden_params': {
        'engine': 'google',
        'max_results': 5,
        'google_api_key': os.getenv('GOOGLE_SEARCH_KEY'),
        'tavily_api_key': os.getenv('TAVILY_API_KEY'),
        'searxng_url': 'http://localhost:8988'
    }
}


# ========== 搜索实现 ==========
@alru_cache(maxsize=500)
async def search(query: str, **kwargs) -> list:
    """统一搜索接口，支持 Google、Tavily、SearxNG"""
    params = {**SEARCH_TOOL_CONFIG['hidden_params'], **kwargs}

    engines = {
        'google': _search_google,
        'tavily': _search_tavily,
        'searxng': _search_searxng
    }

    engine_func = engines.get(params['engine'])
    if not engine_func:
        return [{'error': f'Unknown engine: {params["engine"]}'}]

    return await engine_func(query, params)


async def _search_google(query: str, params: dict) -> list:
    """Google Serper API"""
    api_key = params['google_api_key']
    if not api_key:
        return [{'error': 'Google API key not provided'}]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    'https://google.serper.dev/search',
                    headers={'X-API-KEY': api_key},
                    json={'q': query, 'num': params['max_results']},
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                return [
                    {
                        'title': r.get('title', ''),
                        'url': r.get('link', ''),
                        'snippet': r.get('snippet', '')
                    }
                    for r in data.get('organic', [])[:params['max_results']]
                ]
    except Exception as e:
        return [{'error': f'Google search error: {e}'}]


async def _search_tavily(query: str, params: dict) -> list:
    """Tavily API"""
    api_key = params['tavily_api_key']
    if not api_key:
        return [{'error': 'Tavily API key not provided'}]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    'https://api.tavily.com/search',
                    json={
                        'api_key': api_key,
                        'query': query,
                        'search_depth': 'advanced',
                        'max_results': params['max_results']
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                return [
                    {
                        'title': r.get('title', ''),
                        'url': r.get('url', ''),
                        'snippet': r.get('content', '')
                    }
                    for r in data.get('results', [])
                ]
    except Exception as e:
        return [{'error': f'Tavily search error: {e}'}]


async def _search_searxng(query: str, params: dict) -> list:
    """SearxNG instance"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{params['searxng_url']}/search",
                    params={'q': query, 'format': 'json'},
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                return [
                    {
                        'title': r.get('title', ''),
                        'url': r.get('url', ''),
                        'snippet': r.get('content', '')
                    }
                    for r in data.get('results', [])[:params['max_results']]
                ]
    except Exception as e:
        return [{'error': f'SearxNG search error: {e}'}]


# ========== 导出 ==========
def get_tool_config() -> Dict[str, Any]:
    return {**SEARCH_TOOL_CONFIG, 'func': search}