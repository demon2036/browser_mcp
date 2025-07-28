#!/usr/bin/env python3
"""MCP 异步一体化服务器 - 支持高并发"""
import hashlib
import inspect
import json
import time
from functools import wraps, partial
from typing import Any, Optional, Dict, List, Callable

from mcp_module.server.fastmcp import FastMCP

from mcp_module.web.fetch import fetch_chunked
from mcp_module.web.search import searxng_search


# ========== MCP 异步基类 ==========
class AsyncBaseMCPServer:
    """异步通用 MCP 服务器基类"""

    def __init__(self, name: str, port: Optional[int] = None, enable_cache: bool = True):
        self.name = name
        self.enable_cache = enable_cache
        self._cache: Dict[str, tuple[Any, float]] = {}

        if port:
            self.mcp = FastMCP(name, port=port)
        else:
            self.mcp = FastMCP(name)

    def register_tools(self, functions: List[tuple[Callable, int]]):
        """注册异步函数列表为 MCP 工具"""
        for func, cache_ttl in functions:
            wrapped = self._create_async_cached_wrapper(func, cache_ttl)
            self.mcp.tool()(wrapped)
            # print(f"✅ 注册异步工具: {func.__name__} (缓存: {cache_ttl}s)")

    def _make_cache_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """生成缓存键"""
        sig = inspect.signature(func)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            params = dict(bound.arguments)
            cache_data = {'func': func.__name__, 'params': sorted(params.items())}
            return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        except:
            data = {'func': func.__name__, 'args': args, 'kwargs': sorted(kwargs.items())}
            return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def _create_async_cached_wrapper(self, func: Callable, cache_ttl: int) -> Callable:
        """创建异步缓存包装器"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not self.enable_cache or cache_ttl <= 0:
                return await func(*args, **kwargs)

            cache_key = self._make_cache_key(func, args, kwargs)

            if cache_key in self._cache:
                result, expire_time = self._cache[cache_key]
                if time.time() < expire_time:
                    print(f"[Cache Hit] {func.__name__}")
                    return result
                else:
                    del self._cache[cache_key]

            print(f"[Cache Miss] {func.__name__}")
            result = await func(*args, **kwargs)
            self._cache[cache_key] = (result, time.time() + cache_ttl)

            if len(self._cache) > 100:
                self._cleanup_expired()

            return result

        return wrapper

    def _cleanup_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        self._cache = {k: v for k, v in self._cache.items() if v[1] > current_time}

    def clear_cache(self):
        """清除所有缓存"""
        self._cache.clear()
        print("🧹 缓存已清除")

    def run(self):
        """运行 MCP 服务器"""
        print(f"🚀 启动 {self.name} 异步 MCP 服务器...")
        self.mcp.run(transport='streamable-http')


# ========== 主程序 ==========
if __name__ == "__main__":
    # 配置
    # 搜索服务器
    search_server = AsyncBaseMCPServer("search", port=8000)
    search_server.register_tools([
        (searxng_search, 3600),  # 缓存1小时
        (fetch_chunked, 86400),  # 缓存24小时
    ])
    search_server.run()