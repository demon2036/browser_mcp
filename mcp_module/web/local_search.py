import aiohttp
import json
from typing import Dict, Any
from async_lru import alru_cache

# ========== 工具配置 ==========
LOCAL_SEARCH_CONFIG = {
    'name': 'local_search',
    'description': '本地搜索服务',
    'schema': {
        'type': 'object',
        'properties': {
            'query': {
                'type': 'string',
                'description': '搜索查询'
            }
        },
        'required': ['query']
    },
    'hidden_params': {
        'endpoint': 'http://localhost:8101/search',
        'timeout': 10,
        'top_k': 3  # 默认返回3个结果
    }
}


# ========== 搜索实现 ==========
@alru_cache(maxsize=500)
async def local_search(query: str, **kwargs) -> list:
    """调用本地搜索服务"""
    params = {**LOCAL_SEARCH_CONFIG['hidden_params'], **kwargs}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    params['endpoint'],
                    json={'queries': [query]},
                    timeout=aiohttp.ClientTimeout(total=params['timeout'])
            ) as resp:
                if resp.status == 200:
                    results = await resp.json()
                    # 解析结果并返回top_k个
                    parsed = []
                    for r in results[:1]:  # 单查询返回
                        datas = json.loads(r) if isinstance(r, str) else r

                        # 清理不需要的字段
                        if 'results' in datas:
                            for data in datas['results']:
                                data.pop('<coherence>', None)

                        # if isinstance(datas, list):
                        #     parsed.extend(datas[:params['top_k']])
                        # else:
                        #     parsed.append(datas)

                    return datasda
                return [{'error': f'HTTP {resp.status}'}]
    except Exception as e:
        return [{'error': f'Local search error: {e}'}]


# ========== 导出 ==========
def get_tool_config() -> Dict[str, Any]:
    return {**LOCAL_SEARCH_CONFIG, 'func': local_search}