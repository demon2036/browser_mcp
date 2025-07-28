import asyncio
import json
import os
import re
from typing import Dict, Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from openai import AsyncOpenAI
from playwright.async_api import async_playwright

from .prompt import WEB_SUMMARY_PROMPT, CHUNK_SELECTION_PROMPT, FINAL_SELECTION_PROMPT

# ========== 工具配置 ==========
FETCH_CONFIG = {
    'name': 'fetch',
    'description': '智能提取网页中与查询最相关的内容片段',
    'schema': {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': '要获取的网页URL',
                'format': 'uri'
            },
            'query': {
                'type': 'string',
                'description': '用于筛选相关内容的查询'
            }
        },
        'required': ['url', 'query']
    },
    'hidden_params': {
        'chunk_size': 1024,
        'window_size': 16,  # 16个chunks per window
        'max_per_window': 5,
        'final_max': 10,
        'api_base': os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1'),
        'api_key': os.getenv('OPENAI_API_KEY', 'sk-your-api-key-here'),
        'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    }
}

FETCH_CHUNKED_CONFIG = {
    'name': 'fetch_chunked',
    'description': '获取网页内容并按指定大小切分',
    'schema': {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': '要获取的网页URL',
                'format': 'uri'
            }
        },
        'required': ['url']
    },
    'hidden_params': {
        'chunk_size': 2048  # 默认切分大小
    }
}

FETCH_SUMMARY_CONFIG = {
    'name': 'fetch_summary',
    'description': '获取网页内容并根据查询生成摘要',
    'schema': {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': '要获取的网页URL',
                'format': 'uri'
            },
            'query': {
                'type': 'string',
                'description': '用于指导摘要生成的查询内容'
            }
        },
        'required': ['url', 'query']
    },
    'hidden_params': {
        'api_base': os.getenv('OPENAI_API_BASE', 'https://ms-shpc7pdz-100034032793-sw.gw.ap-shanghai.ti.tencentcs.com/ms-shpc7pdz/v1'),
        'api_key': os.getenv('OPENAI_API_KEY', 'sk-your-api-key-here'),
        'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    }
}


# ========== 异步网页获取函数 ==========
async def fetch_page(url: str) -> dict:
    """异步获取网页内容"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False
                                              ,                                      args=[
                                          '--no-sandbox',
                                          '--disable-blink-features=AutomationControlled',
                                          '--disable-infobars',
                                          '--disable-background-timer-throttling',
                                          '--disable-popup-blocking',
                                          '--disable-backgrounding-occluded-windows',
                                          '--disable-renderer-backgrounding',
                                          '--disable-window-activation',
                                          '--disable-focus-on-load',
                                          '--no-first-run',
                                          '--no-default-browser-check',
                                          '--no-startup-window',
                                          '--window-position=0,0',
                                          # '--window-size=1280,1000',
                                      ]



                                              )
            page = await browser.new_page()
            await page.goto(url, wait_until='domcontentloaded')
            content = await page.inner_text('*')
            await browser.close()
            return {'url': url, 'content': content}
    except Exception as e:
        return {'error': str(e), 'url': url}


async def fetch_chunked(url: str, chunk_size: int = 2000) -> dict:
    """异步获取并切分网页内容"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until='domcontentloaded')
            content = await page.inner_text('*')
            await browser.close()

        # 切分操作在事件循环中执行
        loop = asyncio.get_event_loop()

        def split_content():
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=0,
                length_function=len, separators=["\n\n", "\n", " ", ""]
            )
            chunks = splitter.split_text(content)
            return [f"L{i}\n{chunk}" for i, chunk in enumerate(chunks)]

        formatted_chunks = await loop.run_in_executor(None, split_content)

        return {
            'url': url, 'total_chunks': len(formatted_chunks),
            'chunk_size': chunk_size, 'content': '\n\n'.join(formatted_chunks)
        }
    except Exception as e:
        return {'error': str(e), 'url': url}


async def fetch_summary(
        url: str,
        query: str,
        api_base: str = 'https://api.openai.com/v1',
        api_key: str = 'sk-your-api-key-here',
        model: str = 'gpt-4o-mini'
) -> dict:
    """异步获取网页内容并生成摘要"""
    try:
        # 获取网页内容
        result = await fetch_page(url)
        if 'error' in result:
            return result

        content = result['content']

        # 准备提示词
        prompt = WEB_SUMMARY_PROMPT.format(
            query=query,
            content=content[:35000]
        )



        print(api_base)

        # 初始化 AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base
        )

        # 调用 LLM
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.8,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        )

        summary = response.choices[0].message.content
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()

        return {
            'url': url,
            'query': query,
            'summary': summary,
            'content_length': len(content),
            'model': model
        }

    except Exception as e:
        return {'error': str(e), 'url': url}


async def fetch(
        url: str,
        query: str,
        chunk_size: int = 1024,
        window_size: int = 16,
        max_per_window: int = 5,
        final_max: int = 10,
        api_base: str = 'https://api.openai.com/v1',
        api_key: str = 'sk-your-api-key-here',
        model: str = 'gpt-4o-mini'
) -> dict:
    """智能提取网页相关内容"""
    try:
        # 1. 获取网页内容
        result = await fetch_page(url)
        if 'error' in result:
            return result

        content = result['content']

        # 2. 切分成chunks
        chunks = []
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            chunks.append(chunk)

        if not chunks:
            return {'error': 'No content to process', 'url': url}

        # 3. 创建窗口（不重叠）
        windows = []
        for i in range(0, len(chunks), window_size):
            window = chunks[i:i + window_size]
            window_start = i
            windows.append((window, window_start))

        # 4. 初始化 AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)

        # 5. 并行处理每个窗口
        async def process_window(window_data):
            window_chunks, start_idx = window_data

            # 构建chunks文本
            chunks_text = "\n\n".join([
                f"[{i}]:\n{chunk[:200]}..." if len(chunk) > 200 else f"[{i}]:\n{chunk}"
                for i, chunk in enumerate(window_chunks)
            ])

            prompt = CHUNK_SELECTION_PROMPT.format(
                query=query,
                chunks_text=chunks_text,
                max_selections=max_per_window
            )

            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                top_p=0.8,
                extra_body={
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )

            print(response)


            try:
                # 解析返回的数字列表
                selected = json.loads(response.choices[0].message.content)
                # 转换为全局索引
                return [(start_idx + idx, chunks[start_idx + idx]) for idx in selected if idx < len(window_chunks)]
            except:
                return []

        # 并行执行
        tasks = [process_window(w) for w in windows]
        window_results = await asyncio.gather(*tasks)

        # 合并结果
        all_selected = []
        for selections in window_results:
            all_selected.extend(selections)

        # 去重（保持顺序）
        seen = set()
        unique_selected = []
        for idx, chunk in all_selected:
            if idx not in seen:
                seen.add(idx)
                unique_selected.append((idx, chunk))

        # 6. 第二阶段筛选（如果需要）
        if len(unique_selected) > final_max:
            # 构建已选chunks的文本
            chunks_text = "\n\n".join([
                f"[{i}]:\n{chunk[:200]}..." if len(chunk) > 200 else f"[{i}]:\n{chunk}"
                for i, (_, chunk) in enumerate(unique_selected)
            ])

            prompt = FINAL_SELECTION_PROMPT.format(
                query=query,
                chunks_text=chunks_text,
                final_max=final_max
            )

            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100
            )

            try:
                final_indices = json.loads(response.choices[0].message.content)
                unique_selected = [unique_selected[i] for i in final_indices if i < len(unique_selected)]
            except:
                # 如果解析失败，截取前final_max个
                unique_selected = unique_selected[:final_max]

        # 7. 按原始顺序排序并拼接
        unique_selected.sort(key=lambda x: x[0])
        final_content = "\n\n".join([chunk for _, chunk in unique_selected])

        return {
            'url': url,
            'query': query,
            'selected_chunks': len(unique_selected),
            'total_chunks': len(chunks),
            'content': final_content,
            'model': model
        }

    except Exception as e:
        return {'error': str(e), 'url': url}


# ========== 导出工具配置 ==========
def get_fetch_config() -> Dict[str, Any]:
    """获取 fetch 工具配置"""
    return {
        **FETCH_CONFIG,
        'func': fetch
    }


def get_fetch_chunked_config() -> Dict[str, Any]:
    """获取 fetch_chunked 工具配置"""
    return {
        **FETCH_CHUNKED_CONFIG,
        'func': fetch_chunked
    }


def get_fetch_summary_config() -> Dict[str, Any]:
    """获取 fetch_summary 工具配置"""
    return {
        **FETCH_SUMMARY_CONFIG,
        'func': fetch_summary
    }



