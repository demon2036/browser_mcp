#!/usr/bin/env python3
"""多个 MCP 服务器运行示例"""
import threading
from multiprocessing import Process
from search import MCPSearchServer


# 方法1: 使用多线程
def run_with_threads():
    """使用多线程运行多个服务器"""
    servers = [
        MCPSearchServer(
            search_engine="tavily",
            tavily_api_key="your-key",
            port=8000
        ),
        MCPSearchServer(
            search_engine="searxng",
            searxng_url="http://localhost:8888",
            port=8001
        )
    ]

    threads = []
    for server in servers:
        thread = threading.Thread(target=server.run)
        thread.daemon = True  # 主程序退出时自动结束
        thread.start()
        threads.append(thread)

    print("所有服务器已启动！")

    # 等待所有线程
    for thread in threads:
        thread.join()

